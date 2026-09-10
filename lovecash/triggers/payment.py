import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from decimal import Decimal
from pathlib import Path

from lovecash.bch.cashaddr import to_script, to_scripthash, token_variant
from lovecash.bch.derive import XpubDeriver
from lovecash.bch.electrum import ElectrumClient
from lovecash.bch.pricing import PriceFeed
from lovecash.bch.state import StateStore, default_state_dir
from lovecash.bch.tokens import parse_tx
from lovecash.bch.verify import Outcome, Verifier
from lovecash.config import BchConfig, GoalShowConfig
from lovecash.models import TokenReceipt, TokenRule
from lovecash.triggers.base import EmitFn, TriggerSource
from lovecash.triggers.events import PaymentTrigger
from lovecash.triggers.status import ConnectionState, TipStatus

log = logging.getLogger("lovecash.source.payment")

StatusFn = Callable[[ConnectionState], Awaitable[None]]
AddressFn = Callable[[str, int], Awaitable[None]]
TipStatusFn = Callable[[str, TipStatus, dict], Awaitable[None]]
PotBalanceFn = Callable[[int], Awaitable[None]]


class PaymentSource(TriggerSource):
    def __init__(
        self,
        cfg: BchConfig,
        on_status: StatusFn | None = None,
        on_address: AddressFn | None = None,
        on_tip_status: TipStatusFn | None = None,
        client_factory=None,
        verifier_factory=None,
        state_path: Path | None = None,
        token_rules: list[TokenRule] | None = None,
        goal_show: GoalShowConfig | None = None,
        on_pot_balance: PotBalanceFn | None = None,
    ) -> None:
        self._cfg = cfg
        self._on_status = on_status
        self._on_address = on_address
        self._on_tip_status = on_tip_status
        self._stopped = False
        self._primed = False
        self._server_idx = 0
        self._client: ElectrumClient | None = None
        self._client_factory = client_factory or self._default_factory
        self._deriver: XpubDeriver = XpubDeriver(cfg.xpub, cfg.derivation_branch)
        self._next_index = 0
        self._sh_to_index: dict[str, int] = {}
        # Persisted across restarts (see bch/state.py). Mutate ONLY via
        # _mark_seen/_mark_pending/_clear_pending so every change lands
        # on disk — in-memory-only state is how offline tips get missed
        # or, worse, credited twice.
        self._state = StateStore(
            state_path or default_state_dir() / f"state-{cfg.xpub[-8:]}.json",
            cfg.xpub[-8:],
        )
        self._state_existed = self._state.load()
        self._seen = self._state.seen
        self._pending_conf = self._state.pending_conf
        self._pending_addrs = self._state.pending_addrs
        self._verifying: set[str] = set()
        self._verify_tasks: set[asyncio.Task] = set()
        self._verifier_factory = verifier_factory
        self._price_feed = PriceFeed(cfg.pricing) if cfg.pricing.enabled else None
        self._token_rules: list[TokenRule] = []
        self._require_conf_cats: set[str] = set()
        self.set_token_rules(token_rules or [])
        # Phase 3 goal-show pot: watch-only balance for the overlay goal
        # bar. Kept OUT of _sh_to_index so pot txs never enter the tip
        # pipeline — pledges are not tips.
        self._pot_sh: str | None = (
            to_scripthash(goal_show.address) if goal_show else None
        )
        self._on_pot_balance = on_pot_balance

    def set_token_rules(self, token_rules: list[TokenRule]) -> None:
        """Hot-swap token rules (dashboard settings save)."""
        self._token_rules = token_rules
        self._require_conf_cats = {r.category for r in token_rules if r.require_conf}

    @property
    def source_id(self) -> str:
        return f"bch:{self._cfg.xpub[-8:]}"

    def _require_client(self) -> ElectrumClient:
        if self._client is None:
            raise RuntimeError("no active Electrum connection")
        return self._client

    async def _discover_start_index(self) -> int:
        client = self._require_client()
        highest_used = -1
        i = 0
        consecutive_unused = 0
        while consecutive_unused < self._cfg.gap_limit:
            sh = self._deriver.scripthash(i)
            history = await client.call("blockchain.scripthash.get_history", sh)
            if history:
                highest_used = i
                consecutive_unused = 0
            else:
                consecutive_unused += 1
            i += 1
        start = highest_used + 1
        log.info(
            "Address discovery: highest used index %d, starting at %d",
            highest_used,
            start,
        )
        return start

    def current_address(self) -> str:
        return self._deriver.address(self._next_index)

    def current_tip_address(self) -> str:
        """Address viewers should pay. Token-aware spelling when token
        rules exist, so wallets will let viewers attach CashTokens."""
        addr = self.current_address()
        if self._token_rules:
            return token_variant(addr)
        return addr

    def current_price_usd(self) -> float | None:
        """Fresh verified BCH/USD price, or None when unavailable."""
        return self._price_feed.price_usd if self._price_feed is not None else None

    def _our_addresses(self) -> set[str]:
        addrs = {self._deriver.address(i) for i in self._sh_to_index.values()}
        # Fulcrum's verbose decode may spell token-bearing outputs with
        # the token-aware (z…/r…) address; both decode to the same
        # payload, so count sats under either spelling.
        return {
            payload
            for a in addrs
            for payload in (a.split(":")[-1], token_variant(a).split(":")[-1])
        }

    def _our_scripts(self) -> set[bytes]:
        return {
            to_script(self._deriver.address(i)) for i in self._sh_to_index.values()
        }

    def _extract_token_receipts(self, raw_hex: str) -> list[TokenReceipt]:
        """Token outputs paying our addresses, from the raw tx hex.

        Observer-only: any parse failure degrades to "no tokens" — the
        sats path (verbose decode) is untouched by this parser.
        """
        try:
            outputs = parse_tx(bytes.fromhex(raw_hex))
        except Exception as exc:
            log.warning("token parse failed, ignoring tokens: %s", exc)
            return []
        ours = self._our_scripts()
        return [
            TokenReceipt(
                category=o.token.category,
                amount=o.token.amount,
                nft_capability=o.token.nft_capability,
                commitment=o.token.commitment.hex(),
            )
            for o in outputs
            if o.token is not None and o.script in ours
        ]

    async def _token_receipts(self, client: ElectrumClient, txid: str) -> list[TokenReceipt]:
        if not self._token_rules:
            return []
        try:
            raw = await client.call("blockchain.transaction.get", txid)
        except Exception as exc:
            # Transport failure degrades to "no tokens", same as a parse
            # failure — the sats path must not depend on this fetch.
            log.warning("raw tx fetch failed for %s, ignoring tokens: %s", txid[:12], exc)
            return []
        return self._extract_token_receipts(raw)

    def _default_factory(self, host, port, ssl, tls_verify) -> ElectrumClient:
        return ElectrumClient(
            host,
            port,
            ssl,
            heartbeat_s=self._cfg.heartbeat_seconds,
            tls_verify=tls_verify,
        )

    async def _status(self, state: ConnectionState) -> None:
        if self._on_status:
            await self._on_status(state)

    def _next_server(self):
        pool = self._cfg.servers
        s = pool[self._server_idx % len(pool)]
        self._server_idx += 1
        return s

    async def _subscribe_all(self) -> None:
        client = self._require_client()
        # Extend the map over the fresh window, then (re-)subscribe to
        # EVERY watched address — including ones that rotated out of the
        # window. A new connection has no subscriptions, and dropping
        # rotated-out addresses silently missed late payers tipping an
        # older QR after a reconnect.
        for i in range(self._next_index, self._next_index + self._cfg.gap_limit):
            self._sh_to_index.setdefault(self._deriver.scripthash(i), i)
        for sh, i in self._pending_addrs.items():
            self._sh_to_index.setdefault(sh, i)
        for sh in list(self._sh_to_index):
            await client.subscribe_scripthash(sh)
        if self._pot_sh is not None:
            await client.subscribe_scripthash(self._pot_sh)
            await self._report_pot_balance()

    async def _report_pot_balance(self) -> None:
        client = self._require_client()
        try:
            # Fulcrum hides token-bearing UTXOs unless asked — the pot
            # carries the minting NFT, so a plain get_balance reads 0.
            bal = await client.call(
                "blockchain.scripthash.get_balance", self._pot_sh, "include_tokens"
            )
        except Exception:
            bal = await client.call(
                "blockchain.scripthash.get_balance", self._pot_sh
            )
        total = int(bal.get("confirmed", 0)) + int(bal.get("unconfirmed", 0))
        log.info("Goal pot balance: %d sats", total)
        if self._on_pot_balance:
            await self._on_pot_balance(total)

    async def _listunspent(self, scripthash: str) -> list[dict]:
        """UTXOs for a scripthash, token data included.

        Prefers the Fulcrum CashToken extension ("include_tokens"); falls
        back to plain listunspent + our own raw-tx parse on servers
        without it.
        """
        client = self._require_client()
        try:
            rows = await client.call(
                "blockchain.scripthash.listunspent", scripthash, "include_tokens"
            )
            extended = True
        except Exception:
            rows = await client.call("blockchain.scripthash.listunspent", scripthash)
            extended = False
        out = []
        for row in rows or []:
            if extended:
                td = row.get("token_data")
                token = None
                if td:
                    token = {
                        "category": td["category"],
                        "amount": int(td.get("amount", 0)),
                        "nft": td.get("nft"),
                    }
                out.append(
                    {
                        "tx_hash": row["tx_hash"],
                        "tx_pos": row["tx_pos"],
                        "height": row.get("height", 0),
                        "value": int(row["value"]),
                        "token": token,
                    }
                )
                continue
            raw = await client.call("blockchain.transaction.get", row["tx_hash"])
            outputs = parse_tx(bytes.fromhex(raw))
            o = outputs[row["tx_pos"]]
            token = None
            if o.token is not None:
                token = {
                    "category": o.token.category,
                    "amount": o.token.amount,
                    "nft": (
                        {
                            "capability": o.token.nft_capability,
                            "commitment": o.token.commitment.hex(),
                        }
                        if o.token.nft_capability is not None
                        else None
                    ),
                }
            out.append(
                {
                    "tx_hash": row["tx_hash"],
                    "tx_pos": row["tx_pos"],
                    "height": row.get("height", 0),
                    "value": o.value_sats,
                    "token": token,
                }
            )
        return out

    async def pot_utxo(self) -> dict | None:
        """The live pot UTXO (carries the category's minting NFT)."""
        if self._pot_sh is None:
            return None
        for u in await self._listunspent(self._pot_sh):
            nft = (u["token"] or {}).get("nft") or {}
            if nft.get("capability") == "minting":
                return u
        return None

    async def address_utxos(self, address: str) -> list[dict]:
        """UTXOs paying any address — used by the /tip pledge flow to
        fund the viewer side of a covenant transaction."""
        return await self._listunspent(to_scripthash(address))

    async def current_height(self) -> int:
        client = self._require_client()
        hdr = await client.call("blockchain.headers.subscribe")
        return int(hdr.get("height", 0))

    async def _extend_window(self) -> None:
        client = self._require_client()
        top = self._next_index + self._cfg.gap_limit
        for i in range(self._next_index, top):
            sh = self._deriver.scripthash(i)
            if sh not in self._sh_to_index:
                self._sh_to_index[sh] = i
                await client.subscribe_scripthash(sh)

    async def run(self, emit: EmitFn) -> None:
        if self._price_feed is not None:
            # Fire-and-forget; failures degrade to sats fallback, never block.
            try:
                await self._price_feed.start()
            except Exception as exc:
                log.warning("Price feed failed to start: %s", exc)
        delay = self._cfg.reconnect_min_seconds
        while not self._stopped:
            ok = False
            try:
                ok = await self._session(emit)
            except asyncio.CancelledError:
                raise
            except (ConnectionError, OSError, TimeoutError) as exc:
                log.warning("Electrum session ended: %s", exc)
            if self._stopped:
                break
            await self._status(ConnectionState.RECONNECTING)
            delay = (
                self._cfg.reconnect_min_seconds
                if ok
                else min(delay * 2, self._cfg.reconnect_max_seconds)
            )
            await asyncio.sleep(delay + random.uniform(0, delay * 0.3))  # noqa: S311
        await self._status(ConnectionState.DOWN)

    async def _session(self, emit: EmitFn) -> bool:
        server = self._next_server()
        self._client = self._client_factory(
            server.host, server.port, server.ssl, server.tls_verify
        )
        client = self._client
        await client.connect()

        if not self._primed:
            self._next_index = await self._discover_start_index()
            # Map every used address below the window (no subscriptions —
            # _subscribe_all covers them). Replay and _sum_to_us both
            # need these present.
            for i in range(self._next_index):
                self._sh_to_index.setdefault(self._deriver.scripthash(i), i)
            await self._subscribe_all()
            await self._replay_or_seed(emit)
            self._primed = True
        else:
            await self._subscribe_all()
            await self._scan_all(emit)

        await self._status(ConnectionState.CONNECTED)
        if self._on_address:
            await self._on_address(self.current_tip_address(), self._next_index)
        try:
            while not self._stopped:
                await self._handle_notification(await client.next_notification(), emit)
        finally:
            await client.close()
        return True

    async def _handle_notification(self, notif: dict, emit) -> None:
        # A scripthash notification carries the scripthash that
        # changed — scan just it. Anything unrecognized falls
        # back to a full scan. The goal-show pot only gets a balance
        # refresh: pledges are not tips and never enter the pipeline.
        params = notif.get("params") or []
        sh = params[0] if params and isinstance(params[0], str) else None
        if sh is not None and sh == self._pot_sh:
            await self._report_pot_balance()
        elif sh is not None and sh in self._sh_to_index:
            await self._scan_one(sh, emit)
        else:
            await self._scan_all(emit)

    async def _replay_or_seed(self, emit) -> None:
        """First session only: reconcile tips that arrived while offline.

        With a valid state file, credit anything it has not seen (tier
        rules apply as usual). Without one there is no way to tell a
        missed tip from an already-credited one, so seed the seen-set
        from current history WITHOUT emitting — the fail-safe default is
        to never fire the toy without fresh payment evidence.
        """
        client = self._require_client()
        seeding = not self._state_existed
        replayed = 0
        for i in range(self._next_index):  # the used range below the window
            sh = self._deriver.scripthash(i)
            history = await client.call("blockchain.scripthash.get_history", sh) or []
            for item in history:
                txid = item["tx_hash"]
                if txid in self._seen:
                    continue
                if seeding:
                    self._seen[txid] = None  # assume already handled
                    continue
                await self._process_tx(txid, item.get("height", 0), emit, i, sh)
                replayed += 1
        self._state.save()
        if seeding and self._seen:
            log.info(
                "State initialized: %d historical tx(s) assumed already handled",
                len(self._seen),
            )
        elif replayed:
            log.info("Credited %d tip(s) received while offline", replayed)

    def _mark_seen(self, txid: str) -> None:
        self._seen[txid] = None
        if len(self._seen) > 200_000:
            evicted = next(iter(self._seen))
            del self._seen[evicted]
            log.warning("seen-set full — evicted oldest txid %s", evicted[:12])
        self._state.save()

    def _mark_pending(self, txid: str, sh: str, index: int | None) -> None:
        self._pending_conf[txid] = sh
        if index is not None:
            self._pending_addrs[sh] = index
        self._state.save()

    def _clear_pending(self, txid: str) -> None:
        sh = self._pending_conf.pop(txid, None)
        if sh is None:
            return
        if sh not in self._pending_conf.values():
            self._pending_addrs.pop(sh, None)
        self._state.save()

    async def _scan_one(self, sh: str, emit) -> None:
        client = self._require_client()
        index = self._sh_to_index.get(sh)
        history = await client.call("blockchain.scripthash.get_history", sh) or []
        # A pending tx that vanished from the mempool was double-spent or
        # evicted — nothing left to credit; stop watching it.
        live = {item["tx_hash"] for item in history}
        for txid, psh in list(self._pending_conf.items()):
            if psh == sh and txid not in live:
                log.info("Pending tip %s vanished from mempool", txid[:12])
                self._clear_pending(txid)
        for item in history:
            txid = item["tx_hash"]
            # Pending tips are NOT skipped: their address only rescans
            # when its status changes, and _process_tx credits them the
            # moment the confirmation lands.
            if txid in self._seen or txid in self._verifying:
                continue
            try:
                await self._process_tx(txid, item.get("height", 0), emit, index, sh)
            except Exception:
                log.exception("process_tx failed for %s", txid)

    async def _scan_all(self, emit) -> None:
        for sh in list(self._sh_to_index):
            await self._scan_one(sh, emit)

    async def _announce_tip(self, tip_id: str, status: TipStatus, extra: dict) -> None:
        if self._on_tip_status is not None:
            try:
                await self._on_tip_status(tip_id, status, extra)
            except Exception as exc:
                log.error("Tip-status observer error: %s", exc)

    def _sum_to_us(self, tx: dict) -> tuple[int, str | None]:
        ours = self._our_addresses()
        amount_sats = 0
        memo: str | None = None
        for vout in tx.get("vout", []):
            spk = vout.get("scriptPubKey", {})
            addrs = spk.get("addresses") or (
                [spk["address"]] if "address" in spk else []
            )
            for a in addrs:
                if a.split(":")[-1] in ours:
                    # str() first: JSON floats must not become money math.
                    amount_sats += int(Decimal(str(vout["value"])) * 100_000_000)
                    break
            if spk.get("type") == "nulldata":
                memo = spk.get("asm")
        return amount_sats, memo

    async def _emit_trigger(
        self, txid, amount_sats, confirmations, memo, emit, index, tokens=None
    ) -> None:
        trig = PaymentTrigger(
            source_id=self.source_id,
            txid=txid,
            amount_sats=amount_sats,
            confirmations=confirmations,
            memo=memo,
            tokens=tokens or [],
        )
        log.info(
            "emitting trigger: %d sats, %d token receipt(s)",
            amount_sats,
            len(tokens or []),
        )
        await emit(trig)
        if index is not None and index >= self._next_index:
            self._next_index = index + 1
            await self._extend_window()
            if self._cfg.rotate_on_payment and self._on_address:
                await self._on_address(self.current_tip_address(), self._next_index)
                log.info("Rotated overlay to index %d", self._next_index)

    async def _process_tx(self, txid, height, emit, index, sh) -> None:
        client = self._require_client()
        tx = await client.call("blockchain.transaction.get", txid, True)
        amount_sats, memo = self._sum_to_us(tx)
        tokens = await self._token_receipts(client, txid)
        if amount_sats <= 0 and not tokens:
            self._mark_seen(txid)
            return
        confirmations = tx.get("confirmations", 0 if height <= 0 else 1)

        # Token tips flagged require_conf wait for a block — token value
        # isn't visible in sats, so the sats tiers can't size the risk.
        if (
            tokens
            and confirmations < 1
            and any(t.category in self._require_conf_cats for t in tokens)
        ):
            if txid not in self._pending_conf:
                self._mark_pending(txid, sh, index)
                await self._announce_tip(
                    txid,
                    TipStatus.CONFIRMING,
                    {
                        "amount_sats": amount_sats,
                        "reason": "token_conf",
                        "tokens": [t.model_dump() for t in tokens],
                    },
                )
            return

        # Instant tier: confirmed, or too small to be worth attacking.
        if confirmations >= 1 or amount_sats <= self._effective_zeroconf_sats():
            self._mark_seen(txid)
            self._clear_pending(txid)
            await self._emit_trigger(
                txid, amount_sats, confirmations, memo, emit, index, tokens
            )
            return

        # Everything below announces "confirming" once, then stays
        # pending until the block lands (see _pending_conf).
        if txid in self._pending_conf:
            return

        # High-value ceiling: DSProof is not enough; always wait for a block.
        if amount_sats >= self._effective_ceiling_sats():
            self._mark_pending(txid, sh, index)
            await self._announce_tip(
                txid,
                TipStatus.CONFIRMING,
                {"amount_sats": amount_sats, "reason": "high_value"},
            )
            return

        # Mid-range without DSProof: straight to waiting for a block.
        if not self._cfg.dsproof_enabled:
            self._mark_pending(txid, sh, index)
            await self._announce_tip(
                txid, TipStatus.CONFIRMING, {"amount_sats": amount_sats}
            )
            return

        # Mid-range: DSProof verification window.
        if txid in self._verifying:
            return
        self._verifying.add(txid)
        task = asyncio.create_task(
            self._verify_then_emit(txid, tx, amount_sats, memo, emit, index, sh, tokens)
        )
        self._verify_tasks.add(task)
        task.add_done_callback(self._verify_tasks.discard)

    async def _verify_then_emit(
        self, txid, tx, amount_sats, memo, emit, index, sh, tokens
    ) -> None:
        try:
            verifier = (self._verifier_factory or self._make_verifier)()
            outcome = await verifier.verify(txid, tx)
            if outcome is Outcome.CREDIT:
                self._mark_seen(txid)
                self._clear_pending(txid)
                await self._emit_trigger(txid, amount_sats, 0, memo, emit, index, tokens)
            else:
                # Refused once: wait for the block, don't verify again.
                self._mark_pending(txid, sh, index)
                await self._announce_tip(
                    txid, TipStatus.CONFIRMING, {"amount_sats": amount_sats}
                )
        except Exception:
            log.exception("verify_then_emit failed for %s", txid)
        finally:
            self._verifying.discard(txid)

    def _make_verifier(self) -> Verifier:
        client = self._require_client()
        return Verifier(
            fetch_tx=lambda txid: client.call("blockchain.transaction.get", txid, True),
            watch=client.watch_dsproof,
            unwatch=client.unwatch_dsproof,
            subscribe=lambda txid: client.call(
                "blockchain.transaction.dsproof.subscribe", txid
            ),
            on_status=self._announce_tip,
            window_seconds=self._cfg.dsproof_window_seconds,
        )

    def _effective_ceiling_sats(self) -> int:
        sats_net = self._cfg.always_confirm_above_sats
        if self._price_feed is None:
            return sats_net
        oracle_sats = self._price_feed.usd_to_sats(
            self._cfg.pricing.always_confirm_above_usd
        )
        if oracle_sats is None:  # stale / down / unverified
            return sats_net
        return min(oracle_sats, sats_net)  # oracle may only TIGHTEN

    def _effective_zeroconf_sats(self) -> int:
        sats_floor = self._cfg.zeroconf_max_sats
        if self._price_feed is None or self._cfg.pricing.zeroconf_max_usd is None:
            return sats_floor
        oracle_sats = self._price_feed.usd_to_sats(self._cfg.pricing.zeroconf_max_usd)
        if oracle_sats is None:
            return sats_floor
        # The instant-floor's safe direction is the opposite: a higher
        # price means a USD floor maps to FEWER sats, so instant-credit
        # covers less — that's safe. Use the oracle value directly here,
        # but never let it EXCEED the sats floor (which would instant-credit
        # more than configured).
        return min(oracle_sats, sats_floor)

    async def close(self) -> None:
        self._stopped = True
        if self._price_feed is not None:
            await self._price_feed.stop()
        for task in self._verify_tasks:
            task.cancel()
        if self._client:
            await self._client.close()
