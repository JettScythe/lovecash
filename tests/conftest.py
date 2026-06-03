import pytest

from lovecash.config import (
    BchConfig,
    Limits,
    LovenseConfig,
    Playback,
    ServerConfig,
    Settings,
)
from lovecash.core.orchestrator import Orchestrator
from lovecash.core.router import ToyRouter
from lovecash.models import Action, TipRule, ToyCommand
from lovecash.safety import SafetyState

XPUB = "xpub6DF5GApwf8FAAoTTwY6Gk2ZXC1uM6kCqqZBBTEC2Bc6ELxQn6ftHxexXxr8RsQpka7racgE7QbVs4JBdCXn7XL63LEF8tAC6u6KrT5eeseS"


class FakeController:
    """Records commands instead of touching hardware."""

    def __init__(self, toy_id: str = "default") -> None:
        self.toy_id = toy_id
        self.commands: list[ToyCommand] = []
        self.stopped = False

    async def run(self, cmd: ToyCommand) -> bool:
        self.commands.append(cmd)
        return True

    async def stop_all(self) -> None:
        self.stopped = True

    async def close(self) -> None:
        pass


@pytest.fixture
def settings() -> Settings:
    return Settings(
        limits=Limits(
            max_strength=12,
            max_duration_s=30,
            min_seconds_between_commands=0,
            playback=Playback.OVERRIDE,
        ),
        lovense=LovenseConfig(),  # legacy single-toy
        bch=BchConfig(xpub=XPUB),
        server=ServerConfig(),
        rules=[
            TipRule(
                name="tease",
                min_sats=1000,
                max_sats=9999,
                action=Action.VIBRATE,
                strength=4,
                duration_s=3,
            ),
            TipRule(
                name="intense",
                min_sats=50000,
                min_confirmations=1,
                action=Action.VIBRATE,
                strength=12,
                duration_s=20,
            ),
        ],
    )


@pytest.fixture
def orch_and_ctrl(settings):
    """Single-toy orchestrator with an injected fake (legacy path)."""
    safety = SafetyState(settings.limits.min_seconds_between_commands)
    ctrl = FakeController("default")
    router = ToyRouter(safety, settings.limits)
    router.add_toy("default", ctrl)
    orch = Orchestrator(settings, router=router)
    return orch, ctrl
