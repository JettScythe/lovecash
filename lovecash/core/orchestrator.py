import logging
from collections.abc import Awaitable, Callable

from lovecash.bch.watcher import PaymentWatcher
from lovecash.config import Settings
from lovecash.core.player import CommandPlayer
from lovecash.engine.rules import RulesEngine
from lovecash.lovense.controller import LovenseController
from lovecash.models import TipEvent
from lovecash.safety import SafetyState

log = logging.getLogger("lovecash.core")

TipObserver = Callable[[TipEvent], Awaitable[None]]


class Orchestrator:
    def __init__(
        self, settings: Settings, controller: LovenseController | None = None
    ) -> None:
        self._settings = settings
        self.safety = SafetyState(settings.limits.min_seconds_between_commands)
        self.controller = controller or LovenseController(
            settings.lovense, settings.limits, self.safety
        )
        self.engine = RulesEngine(settings.rules)
        self.player = CommandPlayer(self.controller, settings.limits)
        self.watcher = PaymentWatcher(settings.bch, self._handle_tip)
        self._observers: list[TipObserver] = []

    def add_observer(self, obs: TipObserver) -> None:
        """Hook for the hosted relay to broadcast tip/overlay events."""
        self._observers.append(obs)

    async def _handle_tip(self, tip: TipEvent) -> None:
        log.info("Tip received: %s", tip.model_dump())
        for obs in self._observers:
            try:
                await obs(tip)
            except Exception as exc:
                log.error("Observer error: %s", exc)

        command = self.engine.resolve(tip)
        if command is None:
            return
        await self.player.submit(command)

    async def run(self) -> None:
        log.info("Orchestrator starting.")
        try:
            await self.watcher.start()
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        self.safety.panic_stop()
        await self.player.stop()
        await self.controller.stop_all()
        await self.controller.close()
        await self.watcher.close()
        log.info("Orchestrator stopped.")
