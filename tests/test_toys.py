"""Known-toy table sanity: every entry must resolve and produce rules
whose strengths fit the action's hardware ceiling."""

import pytest
from pydantic import ValidationError

from lovecash.config import Limits, LovenseConfig
from lovecash.lovense.controller import LovenseController
from lovecash.lovense.toys import CATEGORY_RULES, KNOWN_TOYS
from lovecash.models import Action, TipRule, ToyCommand, action_max_strength
from lovecash.onboard import build_rules, toy_defaults
from lovecash.safety import SafetyState


def test_every_known_toy_resolves_and_builds_valid_rules():
    assert len(KNOWN_TOYS) >= 30
    for key, profile in KNOWN_TOYS.items():
        assert key == profile.name.lower(), f"{key}: key must be the /GetToys name"
        assert toy_defaults(key) == (profile.action, profile.category)
        rules = build_rules(profile.action, profile.category, None, "", False, 20, 3600)
        assert rules, key
        for r in rules:
            cmd = ToyCommand(
                action=Action(r["action"]),
                strength=r["strength"],
                duration_s=r["duration_s"],
            )
            assert cmd.strength <= action_max_strength(cmd.action), (
                f"{key}/{r['name']}: {cmd.strength} over hardware ceiling"
            )


def test_every_category_has_rules():
    assert set(CATEGORY_RULES) >= {p.category for p in KNOWN_TOYS.values()}


def test_dual_channel_toys_default_to_all():
    """A single-channel default would silently waste half the toy."""
    for name in ("nora", "ridge", "max", "max 2", "osci 3", "gravity"):
        assert toy_defaults(name) is not None
        assert toy_defaults(name)[0] is Action.ALL, name


async def test_controller_clamps_pump_to_hardware_ceiling():
    ctrl = LovenseController(
        LovenseConfig(), Limits(max_strength=20, max_duration_s=60), SafetyState()
    )
    clamped = ctrl._clamp(ToyCommand(action=Action.PUMP, strength=20, duration_s=10))
    assert clamped.strength == 3
    clamped = ctrl._clamp(ToyCommand(action=Action.VIBRATE, strength=20, duration_s=10))
    assert clamped.strength == 20
    await ctrl.close()


async def test_controller_clamps_performer_limit_below_hardware_ceiling():
    ctrl = LovenseController(
        LovenseConfig(), Limits(max_strength=5, max_duration_s=60), SafetyState()
    )
    clamped = ctrl._clamp(ToyCommand(action=Action.VIBRATE, strength=20, duration_s=10))
    assert clamped.strength == 5
    await ctrl.close()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("oscillate", Action.OSCILLATE),
        ("Fingering", Action.FINGERING),
        ("SUCTION", Action.SUCTION),
        ("all", Action.ALL),
    ],
)
def test_new_actions_parse_case_insensitively(raw, expected):
    assert Action(raw.strip().capitalize()) == expected


async def test_controller_sends_all_action():
    ctrl = LovenseController(
        LovenseConfig(), Limits(max_strength=20, max_duration_s=60), SafetyState()
    )
    posts = []

    class FakeResp:
        def raise_for_status(self) -> None:
            pass

    async def fake_post(_url, json):  # noqa: A002 - matches httpx api
        posts.append(json)
        return FakeResp()

    ctrl._client.post = fake_post
    ok = await ctrl.run(ToyCommand(action=Action.ALL, strength=12, duration_s=5))
    assert ok is True
    assert posts[0]["action"] == "All:12"
    await ctrl.close()


def test_stroke_rule_round_trips_to_command():
    rule = TipRule(
        name="deep",
        min_sats=1000,
        action=Action.THRUSTING,
        strength=10,
        duration_s=5,
        stroke_min=0,
        stroke_max=30,
    )
    cmd = rule.to_command()
    assert (cmd.stroke_min, cmd.stroke_max) == (0, 30)


@pytest.mark.parametrize(
    "lo,hi,action",
    [
        (0, 10, Action.THRUSTING),  # span < 20: Lovense silently ignores it
        (10, None, Action.THRUSTING),  # one-sided
        (50, 30, Action.THRUSTING),  # min >= max
        (0, 30, Action.VIBRATE),  # stroke only pairs with Thrusting
    ],
)
def test_bad_stroke_ranges_are_rejected(lo, hi, action):
    with pytest.raises(ValidationError):
        TipRule(
            name="bad",
            min_sats=1,
            action=action,
            strength=5,
            duration_s=1,
            stroke_min=lo,
            stroke_max=hi,
        )


async def test_controller_sends_stroke_with_thrusting():
    ctrl = LovenseController(
        LovenseConfig(), Limits(max_strength=20, max_duration_s=60), SafetyState()
    )
    posts = []

    class FakeResp:
        def raise_for_status(self) -> None:
            pass

    async def fake_post(_url, json):  # noqa: A002 - matches httpx api
        posts.append(json)
        return FakeResp()

    ctrl._client.post = fake_post
    ok = await ctrl.run(
        ToyCommand(
            action=Action.THRUSTING,
            strength=10,
            duration_s=5,
            stroke_min=0,
            stroke_max=20,
        )
    )
    assert ok is True
    assert posts[0]["action"] == "Stroke:0-20,Thrusting:10"
    await ctrl.close()
