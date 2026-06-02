import logging

from lovecash.bch.cashaddr import to_scripthash
from lovecash.bch.electrum import ElectrumClient
from lovecash.config import BchConfig
from lovecash.triggers.base import EmitFn, TriggerSource
from lovecash.triggers.events import PaymentTrigger

log = logging.getLogger("lovecash.source.payment")


class PaymentSource(TriggerSource):
    def __init__(self, cfg: BchConfig) -> None:
        self._cfg = cfg
        self._scripthash = to_scripthash(cfg.address)
        self._client = ElectrumClient(
            cfg.electrum_host, cfg.electrum_port, cfg.electrum_ssl
        )
        self._seen: set[str] = set()

    @property
    def source_id(self) -> str:
        return f"bch:{self._cfg.address.split(':')[-1][-8:]}"

    async def run(self, emit: EmitFn) -> None:
        await self._client.connect()
        await self._client.subscribe_scripthash(self._scripthash)
        history = await self._client.call(
            "blockchain.scripthash.get_history", self._scripthash
        )
        for item in history or []:
            self._seen.add(item["tx_hash"])
        log.info("Watching %s", self._cfg.address)
        async for _ in self._client.notifications():
            await self._scan_new(emit)

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
        await self._client.close()
