from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Action(StrEnum):
    VIBRATE = "Vibrate"
    THRUSTING = "Thrusting"
    DEPTH = "Depth"
    ROTATE = "Rotate"
    PUMP = "Pump"
    OSCILLATE = "Oscillate"
    FINGERING = "Fingering"
    SUCTION = "Suction"
    # All = every channel of a multi-function toy at once (e.g. Nora
    # vibrate+rotate, Max 2 vibrate+pump).
    ALL = "All"
    STOP = "Stop"


# Hardware ceiling per action, per the official Lovense Standard API
# (developer.lovense.com/docs/standard-solutions/standard-api.html):
# Pump and Depth are 0-3, everything else is 0-20. The controller clamps
# to this below the performer's own limits, so a rule can never write an
# out-of-range value to a toy (out-of-range strengths are ignored by the
# hardware, which reads exactly like a dead rule).
ACTION_MAX_STRENGTH: dict[Action, int] = {
    Action.PUMP: 3,
    Action.DEPTH: 3,
}


def action_max_strength(action: Action) -> int:
    return ACTION_MAX_STRENGTH.get(action, 20)


# Pattern-command feature letters per the Standard API ("V:1;F:v,r;S:1000#").
# All/Stop have no letter: All = blank F (every function responds), Stop
# is never part of a pattern.
PATTERN_FEATURE_LETTER: dict[Action, str] = {
    Action.VIBRATE: "v",
    Action.ROTATE: "r",
    Action.PUMP: "p",
    Action.THRUSTING: "t",
    Action.FINGERING: "f",
    Action.SUCTION: "s",
    Action.DEPTH: "d",
    Action.OSCILLATE: "o",
}

PresetName = Literal["pulse", "wave", "fireworks", "earthquake"]


class ActionSpec(BaseModel):
    """One extra channel of a multi-channel command (e.g. Rotate while
    the primary action Vibrate is running)."""

    action: Action
    strength: int = Field(ge=0, le=20)


class PositionStep(BaseModel):
    """One PatternV2 keyframe: move the Solace Pro stroker to `pos`
    (0-100) at `ts` milliseconds into the pattern."""

    ts: int = Field(ge=0, le=7200000)  # ms; Lovense hard ceiling
    pos: int = Field(ge=0, le=100)


class CommandFields(BaseModel):
    """The Lovense Standard API surface, shared by rules and commands.

    Exactly one MODE per command:
      - Function (default): action/strength (+ extra_actions channels,
        stroke range, loop_running_s/loop_pause_s, stop_previous)
      - Preset: a named app pattern (pulse/wave/fireworks/earthquake)
      - Pattern: a strength sequence at pattern_interval_ms steps
      - PatternV2: positions keyframes (Solace Pro position control)
    action/strength carry defaults so Preset/Positions rules don't need
    dead fields; they only drive the wire in Function/Pattern modes.
    """

    action: Action = Action.VIBRATE
    strength: int = Field(default=0, ge=0, le=20)  # Lovense 0-20 scale
    duration_s: float = Field(ge=0, le=3600)
    # Function-mode extras ------------------------------------------------
    extra_actions: list[ActionSpec] = []  # more channels, own strengths
    stop_previous: bool = True  # False = stack on the running command
    loop_running_s: float | None = Field(default=None, ge=1)  # loopRunningSec
    loop_pause_s: float | None = Field(default=None, ge=1)  # loopPauseSec
    # Solace Pro stroke range (0-100 travel limits), sent as
    # "Stroke:min-max,Thrusting:n". Both or neither.
    stroke_min: int | None = Field(default=None, ge=0, le=100)
    stroke_max: int | None = Field(default=None, ge=0, le=100)
    # Other modes (mutually exclusive) ------------------------------------
    preset: PresetName | None = None
    pattern: list[int] | None = None  # strengths 0-20, <= 50 steps
    pattern_interval_ms: int = Field(default=1000, ge=100)  # Lovense min
    positions: list[PositionStep] | None = None

    @model_validator(mode="after")
    def _check_modes(self) -> CommandFields:
        _validate_stroke(self.action, self.stroke_min, self.stroke_max)
        if self.action in (Action.ALL, Action.STOP) and self.extra_actions:
            raise ValueError(f"{self.action.value} takes no extra channels")
        seen = {self.action}
        for spec in self.extra_actions:
            if spec.action in (Action.ALL, Action.STOP):
                raise ValueError(f"{spec.action.value} is not a channel action")
            if spec.action in seen:
                raise ValueError(f"duplicate channel: {spec.action.value}")
            seen.add(spec.action)
        modes = [
            self.preset is not None,
            self.pattern is not None,
            self.positions is not None,
        ]
        if sum(modes) > 1:
            raise ValueError("preset, pattern and positions are mutually exclusive")
        if any(modes) and (
            self.stroke_min is not None or self.loop_running_s is not None
        ):
            raise ValueError("stroke/loop are Function-mode only")
        if self.pattern is not None:
            if not self.pattern:
                raise ValueError("pattern must have at least one step")
            if len(self.pattern) > 50:  # Lovense hard limit
                raise ValueError("pattern is capped at 50 steps")
            if any(not 0 <= s <= 20 for s in self.pattern):
                raise ValueError("pattern strengths must be 0-20")
        if self.positions is not None:
            if not self.positions:
                raise ValueError("positions must have at least one keyframe")
            if any(
                b.ts <= a.ts
                for a, b in zip(self.positions, self.positions[1:], strict=False)
            ):
                raise ValueError("position timestamps must be strictly increasing")
        return self

    def channels(self) -> list[ActionSpec]:
        """Primary channel first, then extras — the wire order."""
        return [
            ActionSpec(action=self.action, strength=self.strength),
            *self.extra_actions,
        ]

    def _command_payload(self) -> dict:
        return {f: getattr(self, f) for f in CommandFields.model_fields}


def _validate_stroke(
    action: Action,
    stroke_min: int | None,
    stroke_max: int | None,
) -> None:
    """Shared rule-side stroke validation.

    Lovense silently IGNORES a Stroke command whose span is under 20 —
    a dead rule that looks configured, so it's a hard error here. Stroke
    only does anything when paired with Thrusting on the wire.
    """
    if stroke_min is None and stroke_max is None:
        return
    if stroke_min is None or stroke_max is None:
        raise ValueError("stroke_min and stroke_max must be set together")
    if not stroke_min < stroke_max:
        raise ValueError("stroke_min must be < stroke_max")
    if stroke_max - stroke_min < 20:
        raise ValueError("stroke range must span at least 20 (Lovense ignores less)")
    if action != Action.THRUSTING:
        raise ValueError("stroke range only applies to Thrusting rules")


class ToyCommand(CommandFields):
    """A single, already-clamped instruction for a toy."""


class TipRule(CommandFields):
    """Performer-authored mapping from a tip range to a toy action."""

    name: str
    min_sats: int = Field(ge=0)
    max_sats: int = Field(default=2**63 - 1, ge=0)
    toy: str | None = None

    @model_validator(mode="after")
    def _check_range(self) -> TipRule:
        if self.max_sats < self.min_sats:
            raise ValueError("max_sats must be >= min_sats")
        return self

    def matches(self, tip) -> bool:
        return self.min_sats <= tip.amount_sats <= self.max_sats

    def to_command(self) -> ToyCommand:
        return ToyCommand(**self._command_payload())


_CATEGORY_RE = re.compile(r"^[0-9a-f]{64}$")


class TokenReceipt(BaseModel):
    """CashToken contents of one output paying us, extracted from raw tx."""

    category: str  # 64-hex, display byte order
    amount: int = Field(default=0, ge=0)  # fungible base units
    nft_capability: Literal["none", "mutable", "minting"] | None = None
    commitment: str = ""  # NFT commitment, hex


class TokenRule(CommandFields):
    """Performer-authored mapping from a token tip range to a toy action.

    Amounts are in the token's BASE units (see the token's `decimals` in
    its BCMR metadata). Category hex is the identity — never a ticker.
    """

    name: str
    category: str  # 64-hex token category ID, display byte order
    min_amount: int = Field(ge=1)
    max_amount: int = Field(default=2**63 - 1, ge=1)
    # ponytail: wait for 1 confirmation by default. DSProof covers token
    # double-spends (it's a tx-level proof); add a dsproof tier when a
    # performer actually asks for instant token tips.
    require_conf: bool = True
    toy: str | None = None

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, v: str) -> str:
        v = str(v).strip().lower()
        if not _CATEGORY_RE.match(v):
            raise ValueError("category must be 64 lowercase hex chars")
        return v

    @model_validator(mode="after")
    def _check_range(self) -> TokenRule:
        if self.max_amount < self.min_amount:
            raise ValueError("max_amount must be >= min_amount")
        return self

    def matches(self, receipt: TokenReceipt) -> bool:
        return (
            receipt.category == self.category
            and self.min_amount <= receipt.amount <= self.max_amount
        )

    def to_command(self) -> ToyCommand:
        return ToyCommand(**self._command_payload())
