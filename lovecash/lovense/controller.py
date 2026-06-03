from __future__ import annotations

import logging

import httpx

from lovecash.config import Limits, LovenseConfig
from lovecash.models import ToyCommand
from lovecash.safety import SafetyState

log = logging.getLogger("lovecash.lovense")


class LovenseController:
    """Talks to the local Lovense Connect / Game Mode HTTP API.

    Uses the local endpoint so toy control never round-trips through a
    third-party cloud. All commands are clamped to performer limits and
    gated by SafetyState before they ever reach the device.
    """

    def __init__(
        self,
        cfg: LovenseConfig,
        limits: Limits,
        safety: SafetyState,
        toy_id: str | None = None,
    ) -> None:
        self._cfg = cfg
        self._limits = limits
        self._safety = safety
        # Explicit per-toy id wins over the legacy single cfg.toy_id.
        self._toy_id = toy_id or cfg.toy_id
        scheme = "https" if cfg.use_https else "http"
        self._base = f"{scheme}://{cfg.host}:{cfg.port}"
        self._client = httpx.AsyncClient(verify=False, timeout=5.0)

    async def close(self) -> None:
        await self._client.aclose()

    def _clamp(self, cmd: ToyCommand) -> ToyCommand:
        return ToyCommand(
            action=cmd.action,
            strength=min(cmd.strength, self._limits.max_strength),
            duration_s=min(cmd.duration_s, self._limits.max_duration_s),
        )

    async def run(self, cmd: ToyCommand) -> bool:
        if not await self._safety.allow():
            return False
        safe = self._clamp(cmd)
        payload = {
            "command": "Function",
            "action": f"{safe.action.value}:{safe.strength}",
            "timeSec": safe.duration_s,
            "apiVer": 1,
        }
        # Target this specific toy when we know its id; "default" means
        # let Lovense pick the sole connected toy (legacy behavior).
        if self._toy_id and self._toy_id != "default":
            payload["toy"] = self._toy_id
        try:
            resp = await self._client.post(f"{self._base}/command", json=payload)
            resp.raise_for_status()
            log.info("Toy %s command: %s", self._toy_id or "?", safe.model_dump())
            return True
        except httpx.HTTPError as exc:
            log.error("Toy command failed: %s", exc)
            return False

    async def stop_all(self) -> None:
        """Force-stop the device. Always attempted regardless of safety."""
        payload = {
            "command": "Function",
            "action": "Stop",
            "timeSec": 0,
            "apiVer": 1,
        }
        try:
            await self._client.post(f"{self._base}/command", json=payload)
        except httpx.HTTPError as exc:
            log.error("Stop command failed: %s", exc)
