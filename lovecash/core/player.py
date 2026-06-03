# lovecash/core/player.py
from __future__ import annotations

import asyncio
import logging
from collections import deque

from lovecash.config import Limits, Playback, TrimStrategy
from lovecash.lovense.protocol import ToyController
from lovecash.models import ToyCommand

log = logging.getLogger("lovecash.player")


class CommandPlayer:
    """Owns the toy's timeline.

    QUEUE mode runs commands sequentially for their full clamped duration,
    with a bounded backlog trimmed per the configured strategy. OVERRIDE
    mode fires each command immediately.
    """

    def __init__(self, controller: ToyController, limits: Limits) -> None:
        self._controller = controller
        self._limits = limits
        self._pending: deque[ToyCommand] = deque()
        self._wakeup = asyncio.Event()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._limits.playback is Playback.QUEUE and self._task is None:
            self._task = asyncio.create_task(self._consume())

    def _backlog_seconds(self) -> float:
        cap = self._limits.max_duration_s
        return sum(min(c.duration_s, cap) for c in self._pending)

    async def submit(self, cmd: ToyCommand) -> None:
        if self._limits.playback is Playback.OVERRIDE:
            await self._controller.run(cmd)
            return

        self._enqueue_with_trim(cmd)
        self._wakeup.set()

    def _enqueue_with_trim(self, cmd: ToyCommand) -> None:
        cap = self._limits.max_queue_seconds
        strat = self._limits.trim_strategy
        incoming = min(cmd.duration_s, self._limits.max_duration_s)

        # If even the incoming command alone exceeds the cap, accept it but
        # clear the rest — one over-long command is better than silence.
        if self._backlog_seconds() + incoming <= cap:
            self._pending.append(cmd)
            return

        if strat is TrimStrategy.DROP_NEWEST:
            log.warning("Backlog full (%.0fs cap) — dropping incoming tip action.", cap)
            return

        if strat is TrimStrategy.DROP_OLDEST:
            self._pending.append(cmd)
            dropped = 0
            while self._backlog_seconds() > cap and len(self._pending) > 1:
                self._pending.popleft()
                dropped += 1
            if dropped:
                log.warning("Backlog over %.0fs — dropped %d oldest.", cap, dropped)
            return

        if strat is TrimStrategy.COMPRESS:
            self._pending.append(cmd)
            self._compress_to_fit()
            return

    def _compress_to_fit(self) -> None:
        """Scale every pending command's duration down proportionally so the
        backlog fits the cap, never going below min_compressed_duration_s.
        If compression bottoms out and still overflows, drop oldest."""
        cap = self._limits.max_queue_seconds
        floor = self._limits.min_compressed_duration_s
        max_dur = self._limits.max_duration_s

        total = self._backlog_seconds()
        if total <= cap or total == 0:
            return

        scale = cap / total
        for c in self._pending:
            clamped = min(c.duration_s, max_dur)
            c.duration_s = max(floor, clamped * scale)

        # Floors may have pushed us back over the cap; drop oldest to finish.
        dropped = 0
        while self._backlog_seconds() > cap and len(self._pending) > 1:
            self._pending.popleft()
            dropped += 1
        if dropped:
            log.warning(
                "Compression hit the %.1fs floor — dropped %d oldest.", floor, dropped
            )
        else:
            log.info("Compressed backlog to fit %.0fs cap (scale %.2f).", cap, scale)

    async def _consume(self) -> None:
        while True:
            if not self._pending:
                self._wakeup.clear()
                await self._wakeup.wait()
                continue
            cmd = self._pending.popleft()
            try:
                ran = await self._controller.run(cmd)
                if ran:
                    runtime = min(cmd.duration_s, self._limits.max_duration_s)
                    await asyncio.sleep(runtime)
            except Exception as exc:
                log.error("Playback error: %s", exc)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        self._pending.clear()
