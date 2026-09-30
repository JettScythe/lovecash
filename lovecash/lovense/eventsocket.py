"""Lovense Toy Events API client (game-mode /v1 WebSocket).

Receive-only: this socket streams events FROM the Lovense app; commands
stay on the HTTP Standard API (LovenseController). Lifecycle per the
Lovense docs: connect -> `access` handshake -> `access-granted` -> event
stream, with keepalive in BOTH directions (send {"type":"ping"} every
few seconds; answer an inbound ping with a raw "Pong"). Reconnects with
capped exponential backoff on drop and on `event-closed` (game mode
toggled off).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import websockets

from lovecash.config import LovenseConfig

log = logging.getLogger("lovecash.lovense.events")


class LovenseEventSocket:
    def __init__(
        self,
        cfg: LovenseConfig,
        app_name: str = "lovecash",
        connect: Callable[[str], Any] | None = None,
        ping_interval: float = 5.0,
        backoff_max: float = 30.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._cfg = cfg
        self._app_name = app_name
        self._connect = connect or websockets.connect
        self._ping_interval = ping_interval
        self._backoff_max = backoff_max
        # Injectable so tests can observe/collapse backoff delays. The
        # ping loop uses real asyncio.sleep — keepalive timing is not
        # backoff policy.
        self._sleep = sleep
        self._closed = False
        self._ws: Any = None

    @staticmethod
    def url_for(cfg: LovenseConfig) -> str:
        """HTTPS environments use the dash-host lovense.club domain (the
        app's wildcard-DNS cert); plain HTTP environments hit the IP."""
        if cfg.use_https:
            return f"wss://{cfg.host.replace('.', '-')}.lovense.club:{cfg.port}/v1"
        return f"ws://{cfg.host}:{cfg.port}/v1"

    async def _ping_loop(self, ws) -> None:
        while True:
            await asyncio.sleep(self._ping_interval)
            await ws.send(json.dumps({"type": "ping"}))

    async def events(self) -> AsyncIterator[dict]:
        """Yield parsed event dicts, reconnecting forever until close()."""
        url = self.url_for(self._cfg)
        delay = min(1.0, self._backoff_max)
        while not self._closed:
            try:
                async with self._connect(url) as ws:
                    self._ws = ws
                    delay = min(1.0, self._backoff_max)
                    await ws.send(
                        json.dumps(
                            {"type": "access", "data": {"appName": self._app_name}}
                        )
                    )
                    pinger = asyncio.create_task(self._ping_loop(ws))
                    try:
                        while not self._closed:
                            raw = await ws.recv()
                            try:
                                msg = json.loads(raw)
                            except (TypeError, json.JSONDecodeError):
                                log.warning("event socket: skipping malformed frame")
                                continue
                            mtype = msg.get("type") if isinstance(msg, dict) else None
                            if mtype == "ping":
                                await ws.send("Pong")
                            elif mtype == "pong":
                                pass  # keepalive answer; nothing to do
                            elif mtype == "event-closed":
                                log.info(
                                    "game mode disabled (event-closed); reconnecting"
                                )
                                break
                            else:
                                yield msg
                    finally:
                        pinger.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await pinger
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not self._closed:
                    log.warning("event socket connection failed: %s", exc)
            if self._closed:
                break
            log.info("event socket reconnecting in %.1fs", delay)
            await self._sleep(delay)
            delay = min(delay * 2, self._backoff_max)

    async def close(self) -> None:
        self._closed = True
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
