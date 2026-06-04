from __future__ import annotations

import asyncio

from lovecash.config import Limits, Playback
from lovecash.core.player import CommandPlayer
from lovecash.models import Action, ToyCommand
from lovecash.server.relay import RelayHub


class FakeController:
    async def run(self, cmd: ToyCommand) -> bool:
        return True

    async def stop_all(self) -> None:
        pass

    async def close(self) -> None:
        pass


def _cmd(strength: int, dur: float) -> ToyCommand:
    return ToyCommand(action=Action.VIBRATE, strength=strength, duration_s=dur)


async def test_queue_lifecycle_emits_ordered_statuses():
    events: list[tuple[str, str]] = []

    async def on_status(tip_id, status, extra):
        events.append((tip_id, status))

    player = CommandPlayer(
        FakeController(),
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


async def test_relay_broadcasts_tip_status():
    hub = RelayHub()
    q = hub.register()
    await hub.broadcast(
        {"type": "tip_status", "data": {"id": "x", "status": "queued", "position": 2}}
    )
    msg = await q.get()
    assert "tip_status" in msg
    assert "queued" in msg
    assert '"position": 2' in msg
