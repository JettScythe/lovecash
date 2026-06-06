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

    Defaults to NEEDS_CONF on any uncertainty. Credits only when the tx is
    DSProof-protected AND no proof appears within the window.

    `watch(txid)` returns an asyncio.Event that fires when a proof
    notification arrives; `unwatch(txid)` deregisters it. `subscribe(txid)`
    registers the dsproof subscription and returns the current proof state
    (a non-None result means a proof already exists -> refuse).
    """

    def __init__(
        self,
        fetch_tx: TxFetcher,
        watch: Callable[[str], asyncio.Event],
        unwatch: Callable[[str], None],
        subscribe: Callable[[str], Awaitable[object]],
        on_status: StatusEmit | None = None,
        window_seconds: float = 5.0,
    ) -> None:
        self._fetch_tx = fetch_tx
        self._watch = watch
        self._unwatch = unwatch
        self._subscribe = subscribe
        self._on_status = on_status
        self._window = window_seconds

    async def verify(self, txid: str, tx: dict) -> Outcome:
        protection = await analyze_protection(tx, self._fetch_tx)
        if protection is not Protection.PROTECTED:
            return Outcome.NEEDS_CONF

        proof_event = self._watch(txid)
        try:
            try:
                sub_result = await self._subscribe(txid)
            except Exception as exc:
                log.error("dsproof.subscribe failed for %s: %s -> conf", txid[:12], exc)
                return Outcome.NEEDS_CONF

            # The subscribe RESPONSE itself carries a proof if one already
            # exists (confirmed against real mainnet behavior). A non-None
            # result means a proof is present right now.
            if sub_result is not None:
                log.warning("Proof present at subscribe for %s -> conf", txid[:12])
                return Outcome.NEEDS_CONF

            await self._emit(txid, "verifying", {"window_seconds": self._window})
            try:
                await asyncio.wait_for(proof_event.wait(), self._window)
                return Outcome.NEEDS_CONF  # push fired = proof arrived
            except TimeoutError:
                return Outcome.CREDIT  # clean window
        finally:
            self._unwatch(txid)

    async def _emit(self, txid: str, status: str, extra: dict) -> None:
        if self._on_status is not None:
            try:
                await self._on_status(txid, status, extra)
            except Exception as exc:
                log.error("Verify status emit error: %s", exc)
