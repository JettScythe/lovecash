"""Toy-event trigger source: parses Lovense game-mode socket frames into
triggers (rule-able events) and status updates (dashboard-facing)."""

import logging
from collections.abc import Awaitable, Callable

from lovecash.config import LovenseConfig
from lovecash.lovense.eventsocket import LovenseEventSocket
from lovecash.models import ToyEventKind
from lovecash.triggers.base import EmitFn, TriggerSource
from lovecash.triggers.events import ToyEventTrigger, ToyStatus

log = logging.getLogger("lovecash.triggers.toy_events")

ToyStatusFn = Callable[[ToyStatus], Awaitable[None]]

_KIND_MAP = {
    "shake": ToyEventKind.SHAKE,
    "button-pressed": ToyEventKind.BUTTON_PRESSED,
    "depth-changed": ToyEventKind.DEPTH_CHANGED,
    "motion-changed": ToyEventKind.MOTION_CHANGED,
}


def parse_event(msg: dict) -> list[ToyEventTrigger | ToyStatus]:
    """Map one socket frame to triggers/statuses. [] for ignored frames
    (button-down/up, strength/shake-frequency changes) and malformed
    payloads — a bad frame must never kill the consumer loop."""
    mtype = msg.get("type")
    toy_id = msg.get("toyId")
    data = msg.get("data") or {}

    if mtype == "toy-list":
        return [
            ToyStatus(
                toy_id=t["id"],
                name=t.get("name"),
                battery=t.get("battery"),
                connected=t.get("connected"),
            )
            for t in msg.get("toyList") or []
            if isinstance(t, dict) and "id" in t
        ]
    if not isinstance(toy_id, str):
        return []
    if mtype == "toy-status":
        return [ToyStatus(toy_id=toy_id, connected=data.get("connected"))]
    if mtype == "battery-changed":
        return [ToyStatus(toy_id=toy_id, battery=data.get("value"))]
    kind = _KIND_MAP.get(mtype or "")
    if kind is None:
        return []
    if kind is ToyEventKind.MOTION_CHANGED:
        speeds = [
            s.get("speed", 0)
            for s in data.get("motionData") or []
            if isinstance(s, dict)
        ]
        if not speeds:
            return []
        return [ToyEventTrigger(event=kind, toy_id=toy_id, value=max(speeds))]
    if kind is ToyEventKind.DEPTH_CHANGED:
        return [ToyEventTrigger(event=kind, toy_id=toy_id, value=data.get("value"))]
    if kind is ToyEventKind.BUTTON_PRESSED:
        return [
            ToyEventTrigger(
                event=kind, toy_id=toy_id, button_index=data.get("index")
            )
        ]
    return [ToyEventTrigger(event=kind, toy_id=toy_id)]


class ToyEventSource(TriggerSource):
    """Streams toy events from the game-mode socket into the trigger
    queue. Status events bypass the queue: they can never fire rules."""

    def __init__(
        self,
        cfg: LovenseConfig,
        on_toy_status: ToyStatusFn | None = None,
        connect=None,
    ) -> None:
        self._socket = LovenseEventSocket(cfg, connect=connect)
        self._on_status = on_toy_status

    @property
    def source_id(self) -> str:
        return "toy-events"

    async def run(self, emit: EmitFn) -> None:
        async for msg in self._socket.events():
            for parsed in parse_event(msg):
                if isinstance(parsed, ToyEventTrigger):
                    await emit(parsed)
                elif self._on_status is not None:
                    await self._on_status(parsed)

    async def close(self) -> None:
        await self._socket.close()
