from typing import Literal

from pydantic import BaseModel, Field

from lovecash.models import TokenReceipt


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


TriggerEvent = PaymentTrigger
