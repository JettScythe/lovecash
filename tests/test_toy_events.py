"""Toy events pipeline: event models, EventRule matching, socket client,
source routing, orchestrator wiring (issue #20 piece 1)."""

from pydantic import TypeAdapter

from lovecash.models import ToyEventKind
from lovecash.triggers.events import (
    PaymentTrigger,
    ToyEventTrigger,
    TriggerEvent,
)


def test_trigger_union_discriminates():
    trig = ToyEventTrigger(event=ToyEventKind.SHAKE, toy_id="abc")
    assert trig.kind == "toy_event"
    assert trig.value is None
    assert trig.button_index is None

    adapter = TypeAdapter(TriggerEvent)
    payment = adapter.validate_python(
        {
            "kind": "payment",
            "source_id": "s",
            "txid": "t",
            "amount_sats": 1,
            "confirmations": 0,
        }
    )
    assert isinstance(payment, PaymentTrigger)
    toy = adapter.validate_python(
        {"kind": "toy_event", "event": "shake", "toy_id": "abc"}
    )
    assert isinstance(toy, ToyEventTrigger)
    assert toy.event is ToyEventKind.SHAKE
