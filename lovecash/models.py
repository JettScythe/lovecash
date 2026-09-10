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


_CATEGORY_RE = re.compile(r"^[0-9a-f]{64}$")


class TokenReceipt(BaseModel):
    """CashToken contents of one output paying us, extracted from raw tx."""

    category: str  # 64-hex, display byte order
    amount: int = Field(default=0, ge=0)  # fungible base units
    nft_capability: Literal["none", "mutable", "minting"] | None = None
    commitment: str = ""  # NFT commitment, hex


class TokenRule(BaseModel):
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
    action: Action
    strength: int = Field(ge=0, le=20)
    duration_s: float = Field(ge=0, le=3600)
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
        return ToyCommand(
            action=self.action,
            strength=self.strength,
            duration_s=self.duration_s,
        )
