import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

from lovecash.bch.cashaddr import to_scripthash
from lovecash.bch.electrum import ElectrumClient
from lovecash.config import BchConfig
from lovecash.triggers.base import EmitFn, TriggerSource
from lovecash.triggers.events import PaymentTrigger
from lovecash.triggers.status import ConnectionState

log = logging.getLogger("lovecash.source.payment")
StatusFn = Callable[[ConnectionState], Awaitable[None]]


class PaymentSource(TriggerSource):
    def __init__(
        self,
        cfg: BchConfig,
        on_status: StatusFn | None = None,
        client_factory: Callable[..., ElectrumClient] | None = None,
    ) -> None:
        self._cfg = cfg
        self._scripthash = to_scripthash(cfg.address)
        self._seen: set[str] = set()
        self._primed = False
        self._stopped = False
        self._on_status = on_status
        self._server_idx = 0
        self._client: ElectrumClient | None = None
        self._client_factory = client_factory or self._default_factory

    @property
    def source_id(self) -> str:
        return f"bch:{self._cfg.address.split(':')[-1][-8:]}"

    def _default_factory(self, host, port, ssl) -> ElectrumClient:
        return ElectrumClient(host, port, ssl, heartbeat_s=self._cfg.heartbeat_seconds)

    async def _status(self, state: ConnectionState) -> None:
        if self._on_status:
            await self._on_status(state)

    def _next_server(self):
        pool = self._cfg.server_pool()
        server = pool[self._server_idx % len(pool)]
        self._server_idx += 1
        return server

    async def run(self, emit: EmitFn) -> None:
        delay = self._cfg.reconnect_min_seconds
        while not self._stopped:
            connected_ok = False
            try:
                connected_ok = await self._session(emit)
            except asyncio.CancelledError:
                raise
            except (TimeoutError, ConnectionError, OSError) as exc:
                log.warning("Electrum session ended: %s", exc)
            if self._stopped:
                break
            await self._status(ConnectionState.RECONNECTING)
            # Stable connection that dropped -> retry fast. Never-connected
            # -> keep backing off so we don't hammer a dead server.
            delay = (
                self._cfg.reconnect_min_seconds
                if connected_ok
                else min(delay * 2, self._cfg.reconnect_max_seconds)
            )
            jitter = random.uniform(0, delay * 0.3)  # noqa: S311 - non-crypto backoff jitter
            await asyncio.sleep(delay + jitter)
        await self._status(ConnectionState.DOWN)

    async def _session(self, emit: EmitFn) -> bool:
        """One connect→watch cycle. Returns True if it reached CONNECTED."""
        server = self._next_server()
        self._client = self._client_factory(server.host, server.port, server.ssl)
        await self._client.connect()
        await self._client.subscribe_scripthash(self._scripthash)

        if not self._primed:
            await self._prime()  # swallow existing history once
            self._primed = True
        else:
            await self._scan_new(emit)  # gap recovery after an outage

        await self._status(ConnectionState.CONNECTED)
        try:
            while not self._stopped:
                await self._client.next_notification()
                await self._scan_new(emit)
        finally:
            await self._client.close()
        return True

    async def _prime(self) -> None:
        history = await self._client.call(
            "blockchain.scripthash.get_history", self._scripthash
        )
        for item in history or []:
            self._seen.add(item["tx_hash"])
        log.info("Watching %s (primed %d txs)", self._cfg.address, len(self._seen))

    async def _scan_new(self, emit: EmitFn) -> None:
        history = await self._client.call(
            "blockchain.scripthash.get_history", self._scripthash
        )
        for item in history or []:
            txid = item["tx_hash"]
            if txid in self._seen:
                continue
            self._seen.add(txid)
            trig = await self._build_trigger(txid, item.get("height", 0))
            if trig and trig.amount_sats > 0:
                await emit(trig)

    async def _build_trigger(self, txid: str, height: int) -> PaymentTrigger | None:
        tx = await self._client.call("blockchain.transaction.get", txid, True)
        amount_sats = 0
        memo: str | None = None
        for vout in tx.get("vout", []):
            spk = vout.get("scriptPubKey", {})
            addrs = spk.get("addresses") or (
                [spk["address"]] if "address" in spk else []
            )
            short = self._cfg.address.split(":")[-1]
            if self._cfg.address in addrs or any(short in a for a in addrs):
                amount_sats += round(vout["value"] * 100_000_000)
            if spk.get("type") == "nulldata":
                memo = spk.get("asm")
        confirmations = tx.get("confirmations", 0 if height <= 0 else 1)

        # Performer policy: tiny tips can act on 0-conf, larger ones wait.
        if confirmations == 0 and amount_sats > self._cfg.zeroconf_max_sats:
            self._seen.discard(txid)  # re-check on next notification
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
