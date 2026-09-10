from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Action(StrEnum):
    VIBRATE = "Vibrate"
    THRUSTING = "Thrusting"
    DEPTH = "Depth"
    ROTATE = "Rotate"
    PUMP = "Pump"
    STOP = "Stop"


class ToyCommand(BaseModel):
    """A single, already-clamped instruction for a toy."""

    action: Action
    strength: int = Field(ge=0, le=20)  # Lovense 0-20 scale
    duration_s: float = Field(ge=0, le=3600)


class TipRule(BaseModel):
    """Performer-authored mapping from a tip range to a toy action."""

    name: str
    min_sats: int = Field(ge=0)
    max_sats: int = Field(default=2**63 - 1, ge=0)
    action: Action
    strength: int = Field(ge=0, le=20)
    duration_s: float = Field(ge=0, le=3600)
    toy: str | None = None

    @model_validator(mode="after")
    def _check_range(self) -> TipRule:
        if self.max_sats < self.min_sats:
            raise ValueError("max_sats must be >= min_sats")
        return self

    def matches(self, tip) -> bool:
        return self.min_sats <= tip.amount_sats <= self.max_sats

    def to_command(self) -> ToyCommand:
        return ToyCommand(
            action=self.action,
            strength=self.strength,
            duration_s=self.duration_s,
        )
