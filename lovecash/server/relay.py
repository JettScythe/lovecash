import asyncio
import json
import logging

from lovecash.triggers.events import TriggerEvent

log = logging.getLogger("lovecash.relay")


class RelayHub:
    """Fan-out hub for overlay clients (OBS widgets, dashboards)."""

    def __init__(self) -> None:
        self._clients: set[asyncio.Queue] = set()

    def register(self) -> asyncio.Queue:
        # Bounded: a stalled overlay must not grow memory or block others.
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._clients.add(q)
        return q

    def unregister(self, q: asyncio.Queue) -> None:
        self._clients.discard(q)

    async def broadcast(self, payload: dict) -> None:
        """Fan out an arbitrary JSON payload to all connected overlays."""
        msg = json.dumps(payload)
        for q in list(self._clients):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                log.warning("Overlay client too slow — dropping it.")
                self._clients.discard(q)

    async def broadcast_event(self, event: TriggerEvent) -> None:
        """Forward a trigger to overlays. Only payments drive tip alerts."""
        if event.kind == "payment":
            await self.broadcast(
                {
                    "type": "tip",
                    "data": {
                        "amount_sats": event.amount_sats,
                        "txid": event.txid,
                        "confirmations": event.confirmations,
                    },
                }
            )
