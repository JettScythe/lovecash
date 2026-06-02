from __future__ import annotations

import asyncio
import logging
import time

log = logging.getLogger("lovecash.safety")


class SafetyState:
    """Authoritative gate between incoming events and the hardware.

    The stop flag, once set, blocks ALL commands until a human explicitly
    resumes. This is intentionally not reachable by any payment path.
    """

    def __init__(self, min_interval_s: float = 0.5) -> None:
        self._stopped = asyncio.Event()
        self._min_interval_s = min_interval_s
        self._last_command_ts = 0.0
        self._lock = asyncio.Lock()

    @property
    def stopped(self) -> bool:
        return self._stopped.is_set()

    def panic_stop(self) -> None:
        if not self._stopped.is_set():
            log.warning("PANIC STOP engaged — all toy commands blocked.")
        self._stopped.set()

    def resume(self) -> None:
        if self._stopped.is_set():
            log.info("Resumed by performer.")
        self._stopped.clear()

    async def allow(self) -> bool:
        """Return True if a command may proceed right now."""
        if self._stopped.is_set():
            return False
        async with self._lock:
            now = time.monotonic()
            if now - self._last_command_ts < self._min_interval_s:
                log.debug("Rate-limited: command dropped.")
                return False
            self._last_command_ts = now
            return True
