import asyncio
import json

from lovecash.triggers.events import TriggerEvent


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

    async def broadcast(self, payload: dict) -> None:
        """Fan out an arbitrary JSON payload to all connected overlays."""
        msg = json.dumps(payload)
        for q in list(self._clients):
            await q.put(msg)

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
