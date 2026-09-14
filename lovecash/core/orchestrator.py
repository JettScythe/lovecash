import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

from lovecash.config import Settings
from lovecash.core.router import ToyRouter
from lovecash.engine.rules import RulesEngine
from lovecash.safety import SafetyState
from lovecash.triggers.base import TriggerSource
from lovecash.triggers.events import ToyTarget, TriggerEvent
from lovecash.triggers.payment import PaymentSource
from lovecash.triggers.status import ConnectionState, TipStatus

log = logging.getLogger("lovecash.core")

TriggerObserver = Callable[[TriggerEvent], Awaitable[None]]
StatusObserver = Callable[[ConnectionState], Awaitable[None]]
TipStatusObserver = Callable[[str, TipStatus, dict], Awaitable[None]]
AddressObserver = Callable[[str, int], Awaitable[None]]


class Orchestrator:
    def __init__(self, settings: Settings, router: ToyRouter | None = None) -> None:
        self._settings = settings
        self._observers: list[TriggerObserver] = []
        self._status_observers: list[StatusObserver] = []
        self._tip_status_observers: list[TipStatusObserver] = []
        self._address_observers: list[AddressObserver] = []
        self.connection_state = ConnectionState.CONNECTED

        if router is None:
            safety = SafetyState(settings.limits.min_seconds_between_commands)
            router = ToyRouter.from_settings(
                settings, safety, on_tip_status=self._broadcast_tip_status
            )
        self.router = router
        self.safety = router.safety

        self._engine = RulesEngine(settings.rules, settings.token_rules)
        self.sources: list[TriggerSource] = []
        self._queue: asyncio.Queue[TriggerEvent] = asyncio.Queue()

        self._payment_source = PaymentSource(
            settings.bch,
            on_status=self._broadcast_status,
            on_address=self._broadcast_address,
            on_tip_status=self._broadcast_tip_status,
            token_rules=settings.token_rules,
        )
        self.add_source(self._payment_source)

    def set_rules(self, rules, token_rules=None) -> None:
        """Hot-swap the tip rules (dashboard settings save)."""
        if token_rules is not None:
            self._payment_source.set_token_rules(token_rules)
            self._engine = RulesEngine(rules, token_rules)
        else:
            self._engine = RulesEngine(rules, self._settings.token_rules)

    def add_source(self, source: TriggerSource) -> None:
        self.sources.append(source)

    def add_observer(self, obs: TriggerObserver) -> None:
        self._observers.append(obs)

    def add_status_observer(self, obs: StatusObserver) -> None:
        self._status_observers.append(obs)

    def add_tip_status_observer(self, obs: TipStatusObserver) -> None:
        self._tip_status_observers.append(obs)

    def add_address_observer(self, obs: AddressObserver) -> None:
        self._address_observers.append(obs)

    def current_address(self) -> str:
        return self._payment_source.current_address()

    def current_tip_address(self) -> str:
        """Viewer-facing address (token-aware when token rules exist)."""
        return self._payment_source.current_tip_address()

    def current_price_usd(self) -> float | None:
        return self._payment_source.current_price_usd()

    async def _broadcast_status(self, state: ConnectionState) -> None:
        self.connection_state = state
        for obs in self._status_observers:
            try:
                await obs(state)
            except Exception as exc:
                log.error("Status observer error: %s", exc)

    async def _broadcast_tip_status(
        self, tip_id: str, status: TipStatus, extra: dict
    ) -> None:
        for obs in self._tip_status_observers:
            try:
                await obs(tip_id, status, extra)
            except Exception as exc:
                log.error("Tip-status observer error: %s", exc)

    async def _broadcast_address(self, address: str, index: int) -> None:
        for obs in self._address_observers:
            try:
                await obs(address, index)
            except Exception as exc:
                log.error("Address observer error: %s", exc)

    async def _handle_event(self, event: TriggerEvent) -> None:
        for obs in self._observers:
            try:
                await obs(event)
            except Exception as exc:
                log.error("Observer error: %s", exc)
        for cmd, toy in self._engine.resolve_all(event):
            target = ToyTarget(toy_ids=[toy] if toy else [])
            await self.router.dispatch(cmd, target, tip_id=event.txid)

    async def _consume(self) -> None:
        while True:
            await self._handle_event(await self._queue.get())

    async def run(self) -> None:
        self.router.start()
        consumer = asyncio.create_task(self._consume())
        tasks = [asyncio.create_task(s.run(self._queue.put)) for s in self.sources]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Source task died")
        finally:
            consumer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await consumer
            await self.shutdown()

    async def shutdown(self) -> None:
        self.safety.panic_stop()
        await self.router.stop_all()
        await self.router.close()
        for source in self.sources:
            await source.close()
        log.info("Orchestrator stopped.")
