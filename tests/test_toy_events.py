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


def _engine():
    from lovecash.engine.rules import RulesEngine

    return RulesEngine(
        [],
        event_rules=[
            EventRule(
                name="tease", event=ToyEventKind.DEPTH_CHANGED, duration_s=2,
                min_value=1, max_value=10,
            ),
            EventRule(
                name="intense", event=ToyEventKind.DEPTH_CHANGED, duration_s=2,
                min_value=11, max_value=20,
            ),
            EventRule(name="shaker", event=ToyEventKind.SHAKE, duration_s=2,
                      toy="t2"),
            EventRule(
                name="button1", event=ToyEventKind.BUTTON_PRESSED, duration_s=2,
                button_index=1,
            ),
        ],
    )


def _fired_names(engine, event):
    return [cmd for cmd, _ in engine.resolve_event(event)]


def test_resolve_event_fires_on_band_entry_only():
    engine = _engine()
    assert len(engine.resolve_event(_depth(5))) == 1  # tease enters
    assert engine.resolve_event(_depth(7)) == []  # still in band: no refire
    intense = engine.resolve_event(_depth(15))
    assert len(intense) == 1  # intense enters
    assert len(engine.resolve_event(_depth(3))) == 1  # tease re-enters


def test_resolve_event_tier_and_target():
    engine = _engine()
    fired = engine.resolve_event(_depth(15))
    assert len(fired) == 1
    cmd, target = fired[0]
    assert target is None  # rule's toy is None -> all toys
    assert cmd.duration_s == 2


def test_resolve_event_shake_fires_every_time():
    engine = _engine()
    shake = ToyEventTrigger(event=ToyEventKind.SHAKE, toy_id="zzz")
    for _ in range(2):
        fired = engine.resolve_event(shake)
        assert len(fired) == 1
        assert fired[0][1] == "t2"  # rule targets toy t2


def test_resolve_event_button_index_filter():
    engine = _engine()
    press0 = ToyEventTrigger(
        event=ToyEventKind.BUTTON_PRESSED, toy_id="zzz", button_index=0
    )
    press1 = ToyEventTrigger(
        event=ToyEventKind.BUTTON_PRESSED, toy_id="zzz", button_index=1
    )
    assert engine.resolve_event(press0) == []
    assert len(engine.resolve_event(press1)) == 1


def test_resolve_event_missing_value_no_crash():
    engine = _engine()
    assert engine.resolve_event(_depth(None)) == []  # no fire, no exception
    assert len(engine.resolve_event(_depth(5))) == 1  # edge was out-of-band
