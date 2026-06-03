import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

from lovecash.config import Settings
from lovecash.core.router import ToyRouter
from lovecash.engine.rules import RulesEngine
from lovecash.resolve import DirectResolver, PaymentResolver, Resolver
from lovecash.safety import SafetyState
from lovecash.triggers.base import TriggerSource
from lovecash.triggers.events import TriggerEvent
from lovecash.triggers.payment import PaymentSource
from lovecash.triggers.status import ConnectionState

log = logging.getLogger("lovecash.core")

TriggerObserver = Callable[[TriggerEvent], Awaitable[None]]


class Orchestrator:
    def __init__(self, settings: Settings, router: ToyRouter | None = None) -> None:
        self._settings = settings
        self.safety = SafetyState(settings.limits.min_seconds_between_commands)
        self.router = router or ToyRouter.from_settings(settings, self.safety)
        self.safety = self.router.safety
        self.resolvers: dict[str, Resolver] = {
            "payment": PaymentResolver(RulesEngine(settings.rules)),
            "direct": DirectResolver(),
        }
        self.sources: list[TriggerSource] = []
        self._observers: list[TriggerObserver] = []
        self._queue: asyncio.Queue[TriggerEvent] = asyncio.Queue()
        self._status_observers: list = []
        self.connection_state = ConnectionState.CONNECTED
        self._payment_source = PaymentSource(
            settings.bch, on_status=self._broadcast_status
        )
        self.add_source(self._payment_source)

    def current_address(self) -> str:
        """The address the overlay should display right now."""
        return self._payment_source.current_address()

    def add_status_observer(self, obs) -> None:
        self._status_observers.append(obs)

    async def _broadcast_status(self, state) -> None:
        self.connection_state = state
        for obs in self._status_observers:
            try:
                await obs(state)
            except Exception as exc:
                log.error("Status observer error: %s", exc)

    def add_source(self, source: TriggerSource) -> None:
        self.sources.append(source)

    def add_observer(self, obs: TriggerObserver) -> None:
        self._observers.append(obs)

    async def _emit(self, event: TriggerEvent) -> None:
        await self._queue.put(event)

    async def _handle_event(self, event) -> None:
        for obs in self._observers:
            try:
                await obs(event)
            except Exception as exc:
                log.error("Observer error: %s", exc)
        resolver = self.resolvers.get(event.kind)
        if resolver is None:
            return
        for cmd, target in resolver.resolve(event):
            await self.router.dispatch(cmd, target)

    async def _consume(self) -> None:
        while True:
            await self._handle_event(await self._queue.get())

    async def run(self) -> None:
        self.router.start()
        consumer = asyncio.create_task(self._consume())
        tasks = [asyncio.create_task(s.run(self._emit)) for s in self.sources]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
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
