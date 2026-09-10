from __future__ import annotations

from collections.abc import Awaitable, Callable

from lovecash.config import Limits, Settings
from lovecash.core.player import CommandPlayer
from lovecash.lovense.controller import LovenseController
from lovecash.lovense.protocol import ToyController
from lovecash.models import ToyCommand
from lovecash.safety import SafetyState
from lovecash.triggers.events import ToyTarget
from lovecash.triggers.status import TipStatus

TipStatusFn = Callable[[str, TipStatus, dict], Awaitable[None]]


class ToyRouter:
    def __init__(self, safety: SafetyState, limits: Limits) -> None:
        self.safety = safety
        self._limits = limits
        self._toys: dict[str, tuple[ToyController, CommandPlayer]] = {}

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        safety: SafetyState,
        on_tip_status: TipStatusFn | None = None,
    ) -> ToyRouter:
        router = cls(safety, settings.limits)
        for toy in settings.lovense.resolved_toys():
            eff = settings.limits.for_toy(toy)
            ctrl = LovenseController(settings.lovense, eff, safety, toy_id=toy.toy_id)
            router.add_toy(toy.toy_id, ctrl, on_tip_status=on_tip_status)
        return router

    def add_toy(
        self,
        toy_id: str,
        controller: ToyController,
        on_tip_status: TipStatusFn | None = None,
    ) -> None:
        player = CommandPlayer(controller, self._limits, on_tip_status=on_tip_status)
        self._toys[toy_id] = (controller, player)

    def start(self) -> None:
        for _, player in self._toys.values():
            player.start()

    async def dispatch(
        self, command: ToyCommand, target: ToyTarget, tip_id: str | None = None
    ) -> None:
        for toy_id, (_, player) in self._toys.items():
            if not target.toy_ids or toy_id in target.toy_ids:
                await player.submit(command, tip_id=tip_id)

    async def stop_all(self) -> None:
        for ctrl, player in self._toys.values():
            await player.stop()
            await ctrl.stop_all()

    async def close(self) -> None:
        for ctrl, _ in self._toys.values():
            await ctrl.close()
