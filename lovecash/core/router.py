from __future__ import annotations

from collections.abc import Awaitable, Callable

from lovecash.config import Limits, Settings, ToyConfig
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
        self._toy_cfgs: dict[str, ToyConfig] = {}

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
            router.add_toy(toy.toy_id, ctrl, toy_cfg=toy, on_tip_status=on_tip_status)
        return router

    def add_toy(
        self,
        toy_id: str,
        controller: ToyController,
        toy_cfg: ToyConfig | None = None,
        on_tip_status: TipStatusFn | None = None,
    ) -> None:
        player = CommandPlayer(controller, self._limits, on_tip_status=on_tip_status)
        self._toys[toy_id] = (controller, player)
        self._toy_cfgs[toy_id] = toy_cfg or ToyConfig(toy_id=toy_id)

    def refresh_limits(self) -> None:
        """Push updated base limits into every controller (players hold
        the shared object and see mutations already)."""
        for toy_id, (ctrl, _) in self._toys.items():
            if hasattr(ctrl, "set_limits"):
                ctrl.set_limits(self._limits.for_toy(self._toy_cfgs[toy_id]))

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
