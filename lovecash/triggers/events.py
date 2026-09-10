import time
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from lovecash.models import ToyCommand


class ToyTarget(BaseModel):
    """Which toys an event is for. Empty = all toys."""

    toy_ids: list[str] = []
    tags: list[str] = []  # e.g. "his", "hers"

    def matches(self, toy_id: str, tags: set[str]) -> bool:
        if not self.toy_ids and not self.tags:
            return True
        if toy_id in self.toy_ids:
            return True
        return bool(set(self.tags) & tags)


class _BaseTrigger(BaseModel):
    source_id: str
    created_at: float = Field(default_factory=time.time)
    target: ToyTarget = ToyTarget()


class PaymentTrigger(_BaseTrigger):
    kind: Literal["payment"] = "payment"
    txid: str
    amount_sats: int = Field(ge=0)
    confirmations: int = Field(ge=0)
    memo: str | None = None


class DirectTrigger(_BaseTrigger):
    kind: Literal["direct"] = "direct"
    command: ToyCommand
    actor: str | None = None  # who sent it (e.g. partner's name)


TriggerEvent = Annotated[
    PaymentTrigger | DirectTrigger,
    Field(discriminator="kind"),
]
