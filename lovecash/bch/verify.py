import asyncio
import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum

from lovecash.bch.dsproof import Protection, analyze_protection

log = logging.getLogger("lovecash.verify")

TxFetcher = Callable[[str], Awaitable[dict]]
DsproofGetter = Callable[[str], Awaitable[dict | None]]
StatusEmit = Callable[[str, str, dict], Awaitable[None]]


class Outcome(StrEnum):
    CREDIT = "credit"
    NEEDS_CONF = "needs_conf"


class Verifier:
    """Runs the DSProof safety window for a 0-conf tip, event-driven.

    Defaults to NEEDS_CONF on any uncertainty. Credits only when the tx
    is DSProof-protected AND no proof arrives within the window.

    `watch` registers a txid and returns (asyncio.Event, unwatch_callable).
    `dsproof_get` is the one-shot pre-check before the window opens.
    """

    def __init__(
        self,
        fetch_tx: TxFetcher,
        dsproof_get: DsproofGetter,
        watch: Callable[[str], asyncio.Event],
        unwatch: Callable[[str], None],
        subscribe: Callable[[str], Awaitable[object]],
        on_status: StatusEmit | None = None,
        window_seconds: float = 5.0,
    ) -> None:
        self._fetch_tx = fetch_tx
        self._dsproof_get = dsproof_get
        self._watch = watch
        self._unwatch = unwatch
        self._subscribe = subscribe
        self._on_status = on_status
        self._window = window_seconds

    async def verify(self, txid: str, tx: dict) -> Outcome:
        protection = await analyze_protection(tx, self._fetch_tx)
        if protection is not Protection.PROTECTED:
            log.info("Tip %s not protected (%s) -> needs conf", txid[:12], protection)
            return Outcome.NEEDS_CONF

        # Register interest BEFORE subscribing, so a proof arriving during
        # the subscribe round-trip isn't missed.
        proof_event = self._watch(txid)
        try:
            try:
                await self._subscribe(txid)
            except Exception as exc:
                log.error("dsproof.subscribe failed for %s: %s -> conf", txid[:12], exc)
                return Outcome.NEEDS_CONF

            # A proof may already exist before our window opens.
            if await self._has_proof(txid):
                return Outcome.NEEDS_CONF

            await self._emit(txid, "verifying", {"window_seconds": self._window})
            try:
                await asyncio.wait_for(proof_event.wait(), self._window)
                # Event fired = proof arrived.
                log.warning("DSProof arrived for %s -> needs conf", txid[:12])
                return Outcome.NEEDS_CONF
            except TimeoutError:
                log.info("Tip %s cleared window -> credit", txid[:12])
                return Outcome.CREDIT
        finally:
            self._unwatch(txid)

    async def _has_proof(self, txid: str) -> bool:
        try:
            return await self._dsproof_get(txid) is not None
        except Exception as exc:
            log.error("dsproof.get failed for %s: %s -> conf", txid[:12], exc)
            return True

    async def _emit(self, txid: str, status: str, extra: dict) -> None:
        if self._on_status is not None:
            try:
                await self._on_status(txid, status, extra)
            except Exception as exc:
                log.error("Verify status emit error: %s", exc)
