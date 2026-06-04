import asyncio

from conftest import FakeController

from lovecash.config import Limits, Playback, TrimStrategy
from lovecash.core.player import CommandPlayer
from lovecash.models import Action, ToyCommand


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
    ctrl = FakeController()
    player = CommandPlayer(ctrl, Limits(playback=Playback.QUEUE, max_duration_s=30))
    player.start()
    for s in (1, 2, 3):
        await player.submit(_cmd(s, 0.01))
    await asyncio.sleep(0.3)
    assert [c.strength for c in ctrl.commands] == [1, 2, 3]


def test_drop_oldest_keeps_recent():
    p = _player(TrimStrategy.DROP_OLDEST, cap=15)
    for s in range(1, 6):  # 5 x 10s = 50s, cap 15s
        p._enqueue_with_trim(_cmd(s, 10), f"t{s}")
    assert p._backlog_seconds() <= 15
    # The most recent command (strength 5) must survive.
    assert p._pending[-1][0].strength == 5


def test_drop_newest_rejects_incoming():
    p = _player(TrimStrategy.DROP_NEWEST, cap=15)
    for s in range(1, 6):
        p._enqueue_with_trim(_cmd(s, 10), f"t{s}")
    assert p._backlog_seconds() <= 15
    # Oldest survive; the last accepted is whatever fit before the cap.
    assert p._pending[0][0].strength == 1


def test_compress_keeps_all_when_possible():
    p = _player(TrimStrategy.COMPRESS, cap=15)
    for s in range(1, 4):  # 3 x 10s = 30s -> compress to 15s
        p._enqueue_with_trim(_cmd(s, 10), f"t{s}")
    # All three kept, durations scaled, total within cap.
    assert len(p._pending) == 3
    assert p._backlog_seconds() <= 15.01  # float slack
    assert all(c.duration_s >= 1.0 for c, _ in p._pending)


def test_override_fires_immediately():
    ctrl = FakeController()  # typed FakeController, HAS .commands
    p = CommandPlayer(ctrl, Limits(playback=Playback.OVERRIDE))

    async def go():
        await p.submit(_cmd(7, 5))

    asyncio.run(go())
    assert ctrl.commands[0].strength == 7  # ctrl, not p._controller


async def test_status_lifecycle_announced():
    events: list[tuple[str, str]] = []

    async def on_status(tip_id: str, status: str, extra: dict) -> None:
        events.append((tip_id, status))

    ctrl = FakeController()
    player = CommandPlayer(
        ctrl,
        Limits(playback=Playback.QUEUE, max_duration_s=30),
        on_tip_status=on_status,
    )
    player.start()
    await player.submit(_cmd(5, 0.01), tip_id="abc")
    await asyncio.sleep(0.2)
    statuses = [s for tid, s in events if tid == "abc"]
    assert statuses[0] == "queued"
    assert "active" in statuses
    assert statuses[-1] == "done"


async def test_override_announces_active_then_done():
    events: list[tuple[str, str]] = []

    async def on_status(tip_id: str, status: str, extra: dict) -> None:
        events.append((tip_id, status))

    ctrl = FakeController()
    player = CommandPlayer(
        ctrl, Limits(playback=Playback.OVERRIDE), on_tip_status=on_status
    )
    await player.submit(_cmd(7, 1), tip_id="ovr")
    statuses = [s for tid, s in events if tid == "ovr"]
    assert statuses == ["active", "done"]
