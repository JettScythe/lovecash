import asyncio

from lovecash.config import Playback
from lovecash.core.orchestrator import Orchestrator
from lovecash.models import Action, TipEvent, ToyCommand


class FakeController:
    """Records commands instead of hitting hardware."""

    def __init__(self) -> None:
        self.commands: list[ToyCommand] = []
        self.stopped = False

    async def run(self, cmd: ToyCommand) -> bool:
        self.commands.append(cmd)
        return True

    async def stop_all(self) -> None:
        self.stopped = True

    async def close(self) -> None:
        pass


async def _orch(settings):
    return Orchestrator(settings, controller=FakeController())


async def test_tip_triggers_command(settings):
    orch = await _orch(settings)
    await orch._handle_tip(TipEvent(txid="a", amount_sats=5000, confirmations=1))
    assert len(orch.controller.commands) == 1
    assert orch.controller.commands[0].strength == 4


async def test_unmatched_tip_does_nothing(settings):
    orch = await _orch(settings)
    await orch._handle_tip(TipEvent(txid="a", amount_sats=10, confirmations=1))
    assert orch.controller.commands == []


async def test_high_tier_requires_confirmation(settings):
    orch = await _orch(settings)
    # 60k sats matches 'intense' which needs >=1 conf
    await orch._handle_tip(TipEvent(txid="a", amount_sats=60000, confirmations=0))
    assert orch.controller.commands == []
    await orch._handle_tip(TipEvent(txid="b", amount_sats=60000, confirmations=1))
    assert orch.controller.commands[-1].action == Action.VIBRATE


async def test_observer_error_does_not_break_core(settings):
    orch = await _orch(settings)

    async def bad_observer(_tip: TipEvent) -> None:
        raise RuntimeError("overlay crashed")

    orch.add_observer(bad_observer)
    # Tip still fires the toy despite the broken observer.
    await orch._handle_tip(TipEvent(txid="a", amount_sats=5000, confirmations=1))
    assert len(orch.controller.commands) == 1


async def test_queue_mode_delivers_command(settings):
    settings.limits.playback = Playback.QUEUE
    orch = Orchestrator(settings)
    fake = FakeController()
    orch.controller = fake
    orch.player._controller = fake
    orch.player.start()  # launch the consumer

    await orch._handle_tip(TipEvent(txid="q", amount_sats=5000, confirmations=1))
    await asyncio.sleep(0.2)  # let the queue drain
    assert len(fake.commands) == 1
    await orch.player.stop()
