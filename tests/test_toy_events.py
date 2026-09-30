"""Toy events pipeline: event models, EventRule matching, socket client,
source routing, orchestrator wiring (issue #20 piece 1)."""

import pytest
from pydantic import TypeAdapter, ValidationError

from lovecash.models import Action, EventRule, ToyCommand, ToyEventKind
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


def _depth(value, toy_id="aaa"):
    return ToyEventTrigger(
        event=ToyEventKind.DEPTH_CHANGED, toy_id=toy_id, value=value
    )


def test_event_rule_rejects_narrowed_band_on_shake():
    with pytest.raises(ValidationError, match="band"):
        EventRule(
            name="x", event=ToyEventKind.SHAKE, duration_s=1, min_value=5
        )


def test_event_rule_rejects_button_index_on_depth():
    with pytest.raises(ValidationError, match="button_index"):
        EventRule(
            name="x", event=ToyEventKind.DEPTH_CHANGED, duration_s=1,
            button_index=1,
        )


def test_event_rule_rejects_inverted_band():
    with pytest.raises(ValidationError, match="min_value"):
        EventRule(
            name="x", event=ToyEventKind.DEPTH_CHANGED, duration_s=1,
            min_value=10, max_value=5,
        )


def test_event_rule_matches_and_to_command():
    rule = EventRule(
        name="deep",
        event=ToyEventKind.DEPTH_CHANGED,
        action=Action.VIBRATE,
        strength=9,
        duration_s=4,
        min_value=5,
        max_value=10,
        source_toy="aaa",
        toy="bbb",
    )
    assert rule.matches(_depth(7)) is True
    assert rule.matches(_depth(12)) is False
    assert rule.matches(_depth(7, toy_id="other")) is False
    cmd = rule.to_command()
    assert isinstance(cmd, ToyCommand)
    assert cmd.action is Action.VIBRATE
    assert cmd.strength == 9
    assert cmd.duration_s == 4
