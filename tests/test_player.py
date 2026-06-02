import asyncio

from lovecash.config import Limits, Playback, TrimStrategy
from lovecash.core.player import CommandPlayer
from lovecash.models import Action, ToyCommand


class FakeController:
    def __init__(self) -> None:
        self.commands: list[ToyCommand] = []

    async def run(self, cmd: ToyCommand) -> bool:
        self.commands.append(cmd)
        return True


def _cmd(strength: int, dur: float) -> ToyCommand:
    return ToyCommand(action=Action.VIBRATE, strength=strength, duration_s=dur)


def _player(strategy: TrimStrategy, cap: float = 15.0) -> CommandPlayer:
    limits = Limits(
        playback=Playback.QUEUE,
        max_duration_s=30,
        max_queue_seconds=cap,
        trim_strategy=strategy,
        min_compressed_duration_s=1.0,
    )
    return CommandPlayer(FakeController(), limits)


async def test_queue_runs_in_order():
    p = _player(TrimStrategy.DROP_OLDEST, cap=100)
    p.start()
    for s in (1, 2, 3):
        await p.submit(_cmd(s, 0.05))
    await asyncio.sleep(0.3)
    assert [c.strength for c in p._controller.commands] == [1, 2, 3]


def test_drop_oldest_keeps_recent():
    p = _player(TrimStrategy.DROP_OLDEST, cap=15)
    for s in range(1, 6):  # 5 x 10s = 50s, cap 15s
        p._enqueue_with_trim(_cmd(s, 10))
    assert p._backlog_seconds() <= 15
    # The most recent command (strength 5) must survive.
    assert p._pending[-1].strength == 5


def test_drop_newest_rejects_incoming():
    p = _player(TrimStrategy.DROP_NEWEST, cap=15)
    for s in range(1, 6):
        p._enqueue_with_trim(_cmd(s, 10))
    assert p._backlog_seconds() <= 15
    # Oldest survive; the last accepted is whatever fit before the cap.
    assert p._pending[0].strength == 1


def test_compress_keeps_all_when_possible():
    p = _player(TrimStrategy.COMPRESS, cap=15)
    for s in range(1, 4):  # 3 x 10s = 30s -> compress to 15s
        p._enqueue_with_trim(_cmd(s, 10))
    # All three kept, durations scaled, total within cap.
    assert len(p._pending) == 3
    assert p._backlog_seconds() <= 15.01  # float slack
    assert all(c.duration_s >= 1.0 for c in p._pending)


def test_override_fires_immediately():
    limits = Limits(playback=Playback.OVERRIDE)
    p = CommandPlayer(FakeController(), limits)

    async def go():
        await p.submit(_cmd(7, 5))

    asyncio.run(go())
    assert p._controller.commands[0].strength == 7
