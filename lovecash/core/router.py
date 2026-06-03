from lovecash.config import Settings
from lovecash.core.player import CommandPlayer
from lovecash.lovense.controller import LovenseController
from lovecash.models import ToyCommand
from lovecash.safety import SafetyState
from lovecash.triggers.events import ToyTarget


class ToyRouter:
    def __init__(self, safety: SafetyState, limits) -> None:
        self.safety = safety  # ONE shared stop for all toys
        self._limits = limits
        self._toys: dict[str, tuple[LovenseController, CommandPlayer]] = {}

    @classmethod
    def from_settings(cls, settings: Settings, safety: SafetyState):
        router = cls(safety, settings.limits)
        for toy in settings.lovense.resolved_toys():
            eff = settings.limits.for_toy(toy)
            ctrl = LovenseController(settings.lovense, eff, safety, toy_id=toy.toy_id)
            router.add_toy(toy.toy_id, ctrl)
        return router

    def add_toy(self, toy_id: str, controller: LovenseController) -> None:
        player = CommandPlayer(controller, self._limits)
        self._toys[toy_id] = (controller, player)

    def start(self) -> None:
        for _, player in self._toys.values():
            player.start()

    async def dispatch(self, command: ToyCommand, target: ToyTarget) -> None:
        for toy_id, (_, player) in self._toys.items():
            if not target.toy_ids or toy_id in target.toy_ids:
                await player.submit(command)

    async def stop_all(self) -> None:
        for ctrl, player in self._toys.values():
            await player.stop()
            await ctrl.stop_all()

    async def close(self) -> None:
        for ctrl, _ in self._toys.values():
            await ctrl.close()
