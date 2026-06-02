import logging
from collections.abc import Awaitable, Callable

from lovecash.bch.cashaddr import to_scripthash
from lovecash.bch.electrum import ElectrumClient
from lovecash.config import BchConfig
from lovecash.models import TipEvent

log = logging.getLogger("lovecash.watcher")

TipHandler = Callable[[TipEvent], Awaitable[None]]


class PaymentWatcher:
    """Watches one address and emits TipEvents for new inbound payments."""

    def __init__(self, cfg: BchConfig, on_tip: TipHandler) -> None:
        self._cfg = cfg
        self._on_tip = on_tip
        self._scripthash = to_scripthash(cfg.address)
        self._client = ElectrumClient(
            cfg.electrum_host, cfg.electrum_port, cfg.electrum_ssl
        )
        self._seen: set[str] = set()

    async def start(self) -> None:
        await self._client.connect()
        await self._client.subscribe_scripthash(self._scripthash)
        # Prime 'seen' with existing history so we don't fire on startup.
        history = await self._client.call(
            "blockchain.scripthash.get_history", self._scripthash
        )
        for item in history or []:
            self._seen.add(item["tx_hash"])
        log.info("Watching %s (%d historical txs)", self._cfg.address, len(self._seen))
        await self._listen()

    async def _listen(self) -> None:
        async for _ in self._client.notifications():
            await self._scan_new()

    async def _scan_new(self) -> None:
        history = await self._client.call(
            "blockchain.scripthash.get_history", self._scripthash
        )
        for item in history or []:
            txid = item["tx_hash"]
            if txid in self._seen:
                continue
            self._seen.add(txid)
            tip = await self._build_tip(txid, item.get("height", 0))
            if tip and tip.amount_sats > 0:
                await self._on_tip(tip)

    async def _build_tip(self, txid: str, height: int) -> TipEvent | None:
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
        return TipEvent(
            txid=txid, amount_sats=amount_sats, confirmations=confirmations, memo=memo
        )

    async def close(self) -> None:
        await self._client.close()
