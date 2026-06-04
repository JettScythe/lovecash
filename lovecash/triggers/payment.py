import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

from lovecash.bch.derive import XpubDeriver
from lovecash.bch.electrum import ElectrumClient
from lovecash.bch.verify import Outcome, Verifier
from lovecash.config import BchConfig
from lovecash.triggers.base import EmitFn, TriggerSource
from lovecash.triggers.events import PaymentTrigger
from lovecash.triggers.status import ConnectionState

log = logging.getLogger("lovecash.source.payment")

StatusFn = Callable[[ConnectionState], Awaitable[None]]
AddressFn = Callable[[str, int], Awaitable[None]]
TipStatusFn = Callable[[str, str, dict], Awaitable[None]]


class PaymentSource(TriggerSource):
    def __init__(
        self,
        cfg: BchConfig,
        on_status: StatusFn | None = None,
        on_address: AddressFn | None = None,
        on_tip_status: TipStatusFn | None = None,
        client_factory=None,
        verifier_factory=None,
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
        self._seen: set[str] = set()
        self._verifying: set[str] = set()
        self._verify_tasks: set[asyncio.Task] = set()
        self._verifier_factory = verifier_factory

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

    def _our_addresses(self) -> set[str]:
        addrs = {self._deriver.address(i) for i in self._sh_to_index.values()}
        return {a.split(":")[-1] for a in addrs}

    def _default_factory(self, host, port, ssl) -> ElectrumClient:
        return ElectrumClient(host, port, ssl, heartbeat_s=self._cfg.heartbeat_seconds)

    async def _status(self, state: ConnectionState) -> None:
        if self._on_status:
            await self._on_status(state)

    def _next_server(self):
        pool = self._cfg.server_pool()
        s = pool[self._server_idx % len(pool)]
        self._server_idx += 1
        return s

    async def _subscribe_all(self) -> None:
        client = self._require_client()
        self._sh_to_index.clear()
        for i in range(self._next_index, self._next_index + self._cfg.gap_limit):
            sh = self._deriver.scripthash(i)
            self._sh_to_index[sh] = i
            await client.subscribe_scripthash(sh)

    async def _extend_window(self) -> None:
        client = self._require_client()
        top = self._next_index + self._cfg.gap_limit
        for i in range(self._next_index, top):
            sh = self._deriver.scripthash(i)
            if sh not in self._sh_to_index:
                self._sh_to_index[sh] = i
                await client.subscribe_scripthash(sh)

    async def run(self, emit: EmitFn) -> None:
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
        self._client = self._client_factory(server.host, server.port, server.ssl)
        client = self._client
        await client.connect()

        if not self._primed:
            self._next_index = await self._discover_start_index()
            await self._subscribe_all()
            self._primed = True
        else:
            await self._subscribe_all()
            await self._scan_all(emit)

        await self._status(ConnectionState.CONNECTED)
        if self._on_address:
            await self._on_address(self.current_address(), self._next_index)
        try:
            while not self._stopped:
                await client.next_notification()
                await self._scan_all(emit)
        finally:
            await client.close()
        return True

    def _scripthashes(self) -> list[tuple[int | None, str]]:
        return [(i, sh) for sh, i in self._sh_to_index.items()]

    async def _scan_all(self, emit) -> None:
        client = self._require_client()
        for index, sh in self._scripthashes():
            history = await client.call("blockchain.scripthash.get_history", sh)
            for item in history or []:
                txid = item["tx_hash"]
                if txid in self._seen or txid in self._verifying:
                    continue
                try:
                    await self._process_tx(txid, item.get("height", 0), emit, index)
                except Exception:
                    log.exception("process_tx failed for %s", txid)

    async def _announce_tip(self, tip_id: str, status: str, extra: dict) -> None:
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
                    amount_sats += round(vout["value"] * 100_000_000)
                    break
            if spk.get("type") == "nulldata":
                memo = spk.get("asm")
        return amount_sats, memo

    async def _emit_trigger(
        self, txid, amount_sats, confirmations, memo, emit, index
    ) -> None:
        trig = PaymentTrigger(
            source_id=self.source_id,
            txid=txid,
            amount_sats=amount_sats,
            confirmations=confirmations,
            memo=memo,
        )
        log.info("emitting trigger: %d sats", amount_sats)
        await emit(trig)
        if index is not None and index >= self._next_index:
            self._next_index = index + 1
            await self._extend_window()
            if self._cfg.rotate_on_payment and self._on_address:
                await self._on_address(self.current_address(), self._next_index)
                log.info("Rotated overlay to index %d", self._next_index)

    async def _process_tx(self, txid, height, emit, index) -> None:
        client = self._require_client()
        tx = await client.call("blockchain.transaction.get", txid, True)
        amount_sats, memo = self._sum_to_us(tx)
        if amount_sats <= 0:
            self._seen.add(txid)
            return
        confirmations = tx.get("confirmations", 0 if height <= 0 else 1)

        # Confirmed OR small enough -> credit instantly.
        if confirmations >= 1 or amount_sats <= self._cfg.zeroconf_max_sats:
            self._seen.add(txid)
            await self._emit_trigger(
                txid, amount_sats, confirmations, memo, emit, index
            )
            return

        # High-value 0-conf.
        if not self._cfg.dsproof_enabled:
            await self._announce_tip(txid, "confirming", {"amount_sats": amount_sats})
            return
        if txid in self._verifying:
            return
        self._verifying.add(txid)
        task = asyncio.create_task(
            self._verify_then_emit(txid, tx, amount_sats, memo, emit, index)
        )
        self._verify_tasks.add(task)
        task.add_done_callback(self._verify_tasks.discard)

    async def _verify_then_emit(self, txid, tx, amount_sats, memo, emit, index) -> None:
        try:
            verifier = (self._verifier_factory or self._make_verifier)()
            outcome = await verifier.verify(txid, tx)
            if outcome is Outcome.CREDIT:
                self._seen.add(txid)
                await self._emit_trigger(txid, amount_sats, 0, memo, emit, index)
            else:
                await self._announce_tip(
                    txid, "confirming", {"amount_sats": amount_sats}
                )
        except Exception:
            log.exception("verify_then_emit failed for %s", txid)
        finally:
            self._verifying.discard(txid)

    def _make_verifier(self) -> Verifier:
        client = self._require_client()
        return Verifier(
            fetch_tx=lambda txid: client.call("blockchain.transaction.get", txid, True),
            dsproof_get=lambda txid: client.call(
                "blockchain.transaction.dsproof.get", txid
            ),
            watch=client.watch_dsproof,
            unwatch=client.unwatch_dsproof,
            subscribe=lambda txid: client.call(
                "blockchain.transaction.dsproof.subscribe", txid
            ),
            on_status=self._announce_tip,
            window_seconds=self._cfg.dsproof_window_seconds,
        )

    async def close(self) -> None:
        self._stopped = True
        for task in self._verify_tasks:
            task.cancel()
        if self._client:
            await self._client.close()
