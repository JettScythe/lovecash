from typing import Literal

from pydantic import BaseModel, Field

from lovecash.models import TokenReceipt, ToyEventKind


class ToyTarget(BaseModel):
    """Which toys an event is for. Empty = all toys."""

    toy_ids: list[str] = []


class PaymentTrigger(BaseModel):
    kind: Literal["payment"] = "payment"
    source_id: str
    txid: str
    amount_sats: int = Field(ge=0)
    confirmations: int = Field(ge=0)
    memo: str | None = None
    tokens: list[TokenReceipt] = []  # CashToken outputs paying us


class ToyEventTrigger(BaseModel):
    """A rule-able toy event from the game-mode socket. `value` carries
    depth (0-20) or motion burst intensity (max speed, 0-100); shake and
    button-pressed leave it None."""

    kind: Literal["toy_event"] = "toy_event"
    event: ToyEventKind
    toy_id: str  # source toy
    value: float | None = None
    button_index: int | None = None


class ToyStatus(BaseModel):
    """Dashboard-facing per-toy state from status events. None fields
    mean "no info" — the orchestrator merges field-wise."""

    toy_id: str
    name: str | None = None
    battery: int | None = None
    connected: bool | None = None


TriggerEvent = PaymentTrigger | ToyEventTrigger
