from lovecash.config import Limits, Settings
from lovecash.core.player import CommandPlayer
from lovecash.lovense.controller import LovenseController
from lovecash.models import ToyCommand
from lovecash.safety import SafetyState
from lovecash.triggers.events import ToyTarget


class ToyRouter:
    def __init__(self, safety: SafetyState, limits: Limits) -> None:
        self.safety = safety
        self._limits = limits
        self._toys: dict[str, tuple] = {}

    @classmethod
    def from_settings(cls, settings: Settings, safety: SafetyState) -> "ToyRouter":
        router = cls(safety, settings.limits)
        ctrl = LovenseController(settings.lovense, settings.limits, safety)
        router.add_toy(settings.lovense.toy_id or "default", ctrl)
        return router

    def add_toy(self, toy_id, controller, tags=None) -> None:
        player = CommandPlayer(controller, self._limits)
        self._toys[toy_id] = (controller, player, set(tags or []))

    def start(self) -> None:
        for _, player, _ in self._toys.values():
            player.start()

    async def dispatch(self, command: ToyCommand, target: ToyTarget) -> None:
        for toy_id, (_, player, tags) in self._toys.items():
            if target.matches(toy_id, tags):
                await player.submit(command)

    async def stop_all(self) -> None:
        for ctrl, player, _ in self._toys.values():
            await player.stop()
            await ctrl.stop_all()

    async def close(self) -> None:
        for ctrl, _, _ in self._toys.values():
            await ctrl.close()
