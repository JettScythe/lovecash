import asyncio
import contextlib
import logging
import time

from gp_oracle import OracleClient, OracleId, verify_message_signature

from lovecash.config import PricingConfig

log = logging.getLogger("lovecash.pricing")


class PriceFeed:
    """Caches a verified BCH/USD price for converting USD thresholds to sats.

    Fails conservative: stale, unfetchable, or signature-invalid prices
    return None from usd_to_sats(), forcing callers onto the sats fallback.
    """

    def __init__(self, cfg: PricingConfig) -> None:
        self._cfg = cfg
        self._oracle = OracleId[cfg.oracle]
        self._price: float | None = None
        self._fetched_at = 0.0
        self._task: asyncio.Task | None = None
        self._stopped = False

    def _fetch_sync(self) -> float | None:
        """Blocking fetch; runs in a thread. Returns a verified price or None."""
        try:
            with OracleClient() as client:
                if self._cfg.verify_signature:
                    msg = client.latest_message(self._oracle)
                    if not verify_message_signature(
                        msg.message, msg.signature, msg.public_key
                    ):
                        log.error("Oracle signature INVALID -> price rejected")
                        return None
                return float(client.latest_price(self._oracle).decimal_value)
        except Exception as exc:
            log.warning("Price fetch failed: %s", exc)
            return None

    async def refresh_once(self) -> None:
        price = await asyncio.to_thread(self._fetch_sync)
        if price is not None and price > 0:
            self._price = price
            self._fetched_at = time.monotonic()
            log.info("Price refreshed: $%.2f/BCH", price)

    async def start(self) -> None:
        if not self._cfg.enabled or self._task is not None:
            return
        await self.refresh_once()  # prime before first use
        self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        try:
            while not self._stopped:
                await asyncio.sleep(self._cfg.refresh_seconds)
                await self.refresh_once()
        except asyncio.CancelledError:
            raise

    async def stop(self) -> None:
        self._stopped = True
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def usd_to_sats(self, usd: float) -> int | None:
        if self._price is None or self._price <= 0:
            return None
        age = time.monotonic() - self._fetched_at
        if age > self._cfg.max_staleness_seconds:
            log.warning("Price %.0fs stale -> sats fallback", age)
            return None
        return int((usd / self._price) * 100_000_000)
