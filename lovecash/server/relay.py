import asyncio
import json

from lovecash.models import TipEvent


class RelayHub:
    """Fan-out hub for overlay clients (OBS widgets, dashboards)."""

    def __init__(self) -> None:
        self._clients: set[asyncio.Queue] = set()

    def register(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._clients.add(q)
        return q

    def unregister(self, q: asyncio.Queue) -> None:
        self._clients.discard(q)

    async def broadcast_tip(self, tip: TipEvent) -> None:
        msg = json.dumps({"type": "tip", "data": tip.model_dump()})
        for q in list(self._clients):
            await q.put(msg)
