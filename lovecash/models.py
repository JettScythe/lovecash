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


class TipEvent(BaseModel):
    """A confirmed (or 0-conf) inbound payment to the watched address."""

    txid: str
    amount_sats: int = Field(ge=0)
    confirmations: int = Field(ge=0)
    memo: str | None = None


class TipRule(BaseModel):
    """Performer-authored mapping from a tip range to a toy action."""

    name: str
    min_sats: int = Field(ge=0)
    max_sats: int = Field(default=2**63 - 1, ge=0)
    min_confirmations: int = Field(default=0, ge=0)
    action: Action
    strength: int = Field(ge=0, le=20)
    duration_s: float = Field(ge=0, le=3600)

    @model_validator(mode="after")
    def _check_range(self) -> TipRule:
        if self.max_sats < self.min_sats:
            raise ValueError("max_sats must be >= min_sats")
        return self

    def matches(self, tip: TipEvent) -> bool:
        return (
            self.min_sats <= tip.amount_sats <= self.max_sats
            and tip.confirmations >= self.min_confirmations
        )

    def to_command(self) -> ToyCommand:
        return ToyCommand(
            action=self.action,
            strength=self.strength,
            duration_s=self.duration_s,
        )
