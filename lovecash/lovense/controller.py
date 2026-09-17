import logging

import httpx

from lovecash.config import Limits, LovenseConfig
from lovecash.models import (
    PATTERN_FEATURE_LETTER,
    ActionSpec,
    ToyCommand,
    action_max_strength,
)
from lovecash.safety import SafetyState

log = logging.getLogger("lovecash.lovense")


class LovenseController:
    """Talks to the local Lovense Connect.

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

    def set_limits(self, limits: Limits) -> None:
        """Hot-update the clamp ceilings (dashboard settings save)."""
        self._limits = limits

    def _clamp(self, cmd: ToyCommand) -> ToyCommand:
        # Performer ceiling first, then the hardware ceiling for each
        # channel (Pump/Depth are 0-3 on the wire; out-of-range values
        # are silently ignored by the toy).
        def clamp_strength(action, strength: int) -> int:
            return min(strength, self._limits.max_strength, action_max_strength(action))

        return ToyCommand(
            **{
                **cmd._command_payload(),
                "strength": clamp_strength(cmd.action, cmd.strength),
                "duration_s": min(cmd.duration_s, self._limits.max_duration_s),
                "extra_actions": [
                    ActionSpec(
                        action=s.action,
                        strength=clamp_strength(s.action, s.strength),
                    )
                    for s in cmd.extra_actions
                ],
            }
        )

    @staticmethod
    def _action_string(cmd: ToyCommand) -> str:
        """Function-mode wire format, e.g. "Vibrate:5,Rotate:10" or
        "Stroke:0-20,Thrusting:10"."""
        joined = ",".join(f"{c.action.value}:{c.strength}" for c in cmd.channels())
        if cmd.stroke_min is not None and cmd.stroke_max is not None:
            # Stroke sets the Solace Pro travel range; it must ride along
            # with Thrusting in the same command (Lovense Standard API).
            return f"Stroke:{cmd.stroke_min}-{cmd.stroke_max},{joined}"
        return joined

    def _payload(self, safe: ToyCommand) -> dict:
        """Build the /command payload for the command's mode."""
        if safe.preset is not None:
            return {
                "command": "Preset",
                "name": safe.preset,
                "timeSec": safe.duration_s,
                "apiVer": 1,
            }
        if safe.positions is not None:
            return {
                "command": "PatternV2",
                "type": "InitPlay",
                "actions": [{"ts": p.ts, "pos": p.pos} for p in safe.positions],
                "stopPrevious": 1 if safe.stop_previous else 0,
                "apiVer": 1,
            }
        if safe.pattern is not None:
            feats = ",".join(
                PATTERN_FEATURE_LETTER[c.action]
                for c in safe.channels()
                if c.action in PATTERN_FEATURE_LETTER
            )
            return {
                "command": "Pattern",
                "rule": f"V:1;F:{feats};S:{safe.pattern_interval_ms}#",
                "strength": ";".join(str(s) for s in safe.pattern),
                "timeSec": safe.duration_s,
                "apiVer": 2,
            }
        payload: dict = {
            "command": "Function",
            "action": self._action_string(safe),
            "timeSec": safe.duration_s,
            "apiVer": 1,
        }
        if safe.loop_running_s is not None:
            payload["loopRunningSec"] = safe.loop_running_s
        if safe.loop_pause_s is not None:
            payload["loopPauseSec"] = safe.loop_pause_s
        if not safe.stop_previous:
            payload["stopPrevious"] = 0
        return payload

    async def run(self, cmd: ToyCommand) -> bool:
        if not await self._safety.allow():
            return False
        safe = self._clamp(cmd)
        payload = self._payload(safe)
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

    async def set_position(self, value: int) -> bool:
        """Solace Pro real-time stroker position (0-100).

        For live control loops, not tip rules — tip-driven position
        patterns belong in a rule's `positions` (PatternV2 InitPlay).
        """
        if not 0 <= value <= 100:
            raise ValueError("position must be 0-100")
        if not await self._safety.allow():
            return False
        payload: dict = {
            "command": "Position",
            "value": str(value),
            "apiVer": 1,
        }
        if self._toy_id and self._toy_id != "default":
            payload["toy"] = self._toy_id
        try:
            resp = await self._client.post(f"{self._base}/command", json=payload)
            resp.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            log.error("Position command failed: %s", exc)
            return False

    async def stop_all(self) -> None:
        """Force-stop the device. Always attempted regardless of safety.

        Sends PatternV2 Stop as well as Function Stop — a running
        position pattern does not answer to Function:Stop, and the panic
        stop must halt EVERYTHING.
        """
        try:
            await self._client.post(
                f"{self._base}/command",
                json={"command": "PatternV2", "type": "Stop", "apiVer": 1},
            )
            await self._client.post(
                f"{self._base}/command",
                json={
                    "command": "Function",
                    "action": "Stop",
                    "timeSec": 0,
                    "apiVer": 1,
                },
            )
        except httpx.HTTPError as exc:
            log.error("Stop command failed: %s", exc)
