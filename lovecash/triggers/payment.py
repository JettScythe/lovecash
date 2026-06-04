import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

from lovecash.bch.derive import XpubDeriver
from lovecash.bch.electrum import ElectrumClient
from lovecash.config import BchConfig
from lovecash.triggers.base import EmitFn, TriggerSource
from lovecash.triggers.events import PaymentTrigger
from lovecash.triggers.status import ConnectionState

log = logging.getLogger("lovecash.source.payment")

StatusFn = Callable[[ConnectionState], Awaitable[None]]
AddressFn = Callable[[str, int], Awaitable[None]]  # (address, index)


class PaymentSource(TriggerSource):
    def __init__(
        self,
        cfg: BchConfig,
        on_status: StatusFn | None = None,
        on_address: AddressFn | None = None,
        client_factory=None,
    ) -> None:
        self._cfg = cfg
        self._on_status = on_status
        self._on_address = on_address
        self._stopped = False
        self._primed = False
        self._server_idx = 0
        self._client: ElectrumClient | None = None
        self._client_factory = client_factory or self._default_factory
        self._deriver: XpubDeriver = XpubDeriver(cfg.xpub, cfg.derivation_branch)
        self._next_index = 0
        # index -> scripthash, for the currently-subscribed window
        self._sh_to_index: dict[str, int] = {}
        # txids already emitted, keyed globally (works across indices)
        self._seen: set[str] = set()

    @property
    def source_id(self) -> str:
        ident = self._cfg.xpub
        return f"bch:{ident[-8:]}"

    def _require_client(self) -> ElectrumClient:
        if self._client is None:
            raise RuntimeError("no active Electrum connection")
        return self._client

    async def _discover_start_index(self) -> int:
        """Find the first never-used address by scanning the chain.

        Prevents address reuse across sessions when a performer reuses
        the same xpub: we resume past every address that already has
        history, instead of restarting at index 0.
        """
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
        """The address bodies (without prefix) we currently watch."""
        addrs = {self._deriver.address(i) for i in self._sh_to_index.values()}
        # Compare on the part after 'bitcoincash:' to dodge prefix variance.
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
        """After advancing next_index, subscribe newly-exposed high indices."""
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
            # First connect: discover where to resume, then subscribe.
            self._next_index = await self._discover_start_index()
            await self._subscribe_all()
            self._primed = True
        else:
            # Reconnect: resubscribe and rescan for gap-recovery.
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

    async def _scan_all(self, emit):
        client = self._require_client()
        advanced = False  # MUST be initialized before the loop
        log.info("scan: checking %d scripthashes", len(self._scripthashes()))
        for index, sh in self._scripthashes():
            history = await client.call("blockchain.scripthash.get_history", sh)
            log.info("scan idx=%s sh=%s -> %d txs", index, sh[:12], len(history or []))
            for item in history or []:
                txid = item["tx_hash"]
                if txid in self._seen:
                    continue
                self._seen.add(txid)
                try:
                    trig = await self._build_trigger(txid, item.get("height", 0))
                except Exception:
                    log.exception("build_trigger failed for %s", txid)
                    continue
                if trig and trig.amount_sats > 0:
                    log.info("emitting trigger: %d sats", trig.amount_sats)
                    await emit(trig)
                    if (
                        self._deriver
                        and index is not None
                        and index >= self._next_index
                    ):
                        self._next_index = index + 1
                        advanced = True
        if advanced:
            await self._extend_window()
            if self._cfg.rotate_on_payment and self._on_address:
                await self._on_address(self.current_address(), self._next_index)
                log.info("Rotated overlay to index %d", self._next_index)

    async def _build_trigger(self, txid: str, height: int):
        client = self._require_client()
        tx = await client.call("blockchain.transaction.get", txid, True)
        ours = self._our_addresses()
        amount_sats = 0
        memo = None
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

        confirmations = tx.get("confirmations", 0 if height <= 0 else 1)
        if confirmations == 0 and amount_sats > self._cfg.zeroconf_max_sats:
            self._seen.discard(txid)  # re-check on confirmation
            return None
        return PaymentTrigger(
            source_id=self.source_id,
            txid=txid,
            amount_sats=amount_sats,
            confirmations=confirmations,
            memo=memo,
        )

    async def close(self) -> None:
        self._stopped = True
        if self._client:
            await self._client.close()
