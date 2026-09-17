"""Command-mode coverage: the full Lovense Standard API surface
(multi-channel Function, stopPrevious, loop, Preset, Pattern,
PatternV2 positions, Position) as wired by LovenseController."""

import pytest
from pydantic import ValidationError

from lovecash.config import Limits, LovenseConfig
from lovecash.lovense.controller import LovenseController
from lovecash.models import (
    Action,
    ActionSpec,
    PositionStep,
    TipRule,
    ToyCommand,
)
from lovecash.safety import SafetyState


class FakeResponse:
    def raise_for_status(self) -> None:
        pass


class FakeHttp:
    def __init__(self) -> None:
        self.posts: list[dict] = []

    async def post(self, _url, json):  # noqa: A002 - matches httpx api
        self.posts.append(json)
        return FakeResponse()

    async def aclose(self) -> None:
        pass


@pytest.fixture
async def controller():
    ctrl = LovenseController(
        LovenseConfig(),
        Limits(max_strength=10, max_duration_s=60),
        SafetyState(min_interval_s=0),
    )
    ctrl._client = FakeHttp()
    yield ctrl
    await ctrl.close()


async def _run(ctrl, cmd: ToyCommand) -> dict:
    assert await ctrl.run(cmd) is True
    return ctrl._client.posts[-1]


async def test_multi_channel_wire_format(controller):
    sent = await _run(
        controller,
        ToyCommand(
            action=Action.VIBRATE,
            strength=5,
            duration_s=5,
            extra_actions=[ActionSpec(action=Action.ROTATE, strength=10)],
        ),
    )
    assert sent["action"] == "Vibrate:5,Rotate:10"


async def test_extra_channels_clamped_per_action(controller):
    sent = await _run(
        controller,
        ToyCommand(
            action=Action.VIBRATE,
            strength=20,  # clamped to performer limit 10
            duration_s=5,
            extra_actions=[ActionSpec(action=Action.PUMP, strength=20)],  # -> 3
        ),
    )
    assert sent["action"] == "Vibrate:10,Pump:3"


async def test_stop_previous_and_loop_pass_through(controller):
    sent = await _run(
        controller,
        ToyCommand(
            action=Action.VIBRATE,
            strength=5,
            duration_s=20,
            stop_previous=False,
            loop_running_s=9,
            loop_pause_s=4,
        ),
    )
    assert sent["stopPrevious"] == 0
    assert sent["loopRunningSec"] == 9
    assert sent["loopPauseSec"] == 4


async def test_default_payload_omits_optional_keys(controller):
    sent = await _run(
        controller, ToyCommand(action=Action.VIBRATE, strength=5, duration_s=5)
    )
    assert "stopPrevious" not in sent  # Lovense default is already 1
    assert "loopRunningSec" not in sent


async def test_preset_mode(controller):
    sent = await _run(
        controller,
        ToyCommand(
            action=Action.VIBRATE, strength=5, duration_s=9, preset="earthquake"
        ),
    )
    assert sent["command"] == "Preset"
    assert sent["name"] == "earthquake"
    assert "action" not in sent


async def test_pattern_mode_feature_letters(controller):
    sent = await _run(
        controller,
        ToyCommand(
            action=Action.VIBRATE,
            strength=5,
            duration_s=9,
            extra_actions=[ActionSpec(action=Action.ROTATE, strength=5)],
            pattern=[20, 20, 5, 20, 10],
            pattern_interval_ms=500,
        ),
    )
    assert sent["command"] == "Pattern"
    assert sent["rule"] == "V:1;F:v,r;S:500#"
    assert sent["strength"] == "20;20;5;20;10"
    assert sent["apiVer"] == 2


async def test_pattern_all_means_blank_features(controller):
    sent = await _run(
        controller,
        ToyCommand(action=Action.ALL, strength=5, duration_s=9, pattern=[10]),
    )
    assert sent["rule"] == "V:1;F:;S:1000#"


async def test_positions_mode_is_patternv2_initplay(controller):
    sent = await _run(
        controller,
        ToyCommand(
            action=Action.THRUSTING,
            strength=5,
            duration_s=0,
            positions=[PositionStep(ts=0, pos=10), PositionStep(ts=500, pos=90)],
        ),
    )
    assert sent["command"] == "PatternV2"
    assert sent["type"] == "InitPlay"
    assert sent["actions"] == [{"ts": 0, "pos": 10}, {"ts": 500, "pos": 90}]


async def test_set_position(controller):
    assert await controller.set_position(38) is True
    sent = controller._client.posts[-1]
    assert sent == {"command": "Position", "value": "38", "apiVer": 1}


async def test_set_position_bounds_checked():
    ctrl = LovenseController(LovenseConfig(), Limits(), SafetyState())
    with pytest.raises(ValueError, match="0-100"):
        await ctrl.set_position(101)
    await ctrl.close()


async def test_stop_all_kills_patterns_too(controller):
    await controller.stop_all()
    posts = controller._client.posts
    assert posts[0]["command"] == "PatternV2" and posts[0]["type"] == "Stop"
    assert posts[-1]["action"] == "Stop"


@pytest.mark.parametrize(
    "kwargs,match",
    [
        (
            {"extra_actions": [ActionSpec(action=Action.VIBRATE, strength=1)]},
            "duplicate channel",
        ),
        (
            {"extra_actions": [ActionSpec(action=Action.ALL, strength=1)]},
            "not a channel",
        ),
        (
            {
                "action": Action.ALL,
                "extra_actions": [ActionSpec(action=Action.ROTATE, strength=1)],
            },
            "no extra channels",
        ),
        ({"preset": "pulse", "pattern": [5]}, "mutually exclusive"),
        (
            {
                "action": Action.THRUSTING,
                "preset": "pulse",
                "stroke_min": 0,
                "stroke_max": 20,
            },
            "Function-mode only",
        ),
        ({"pattern": []}, "at least one step"),
        ({"pattern": [1] * 51}, "50 steps"),
        ({"pattern": [21]}, "0-20"),
        ({"pattern_interval_ms": 50, "pattern": [5]}, None),  # pydantic ge=100
        ({"positions": []}, "at least one keyframe"),
        (
            {"positions": [PositionStep(ts=100, pos=1), PositionStep(ts=100, pos=2)]},
            "strictly increasing",
        ),
    ],
)
def test_invalid_combinations_rejected(kwargs, match):
    base = {"action": Action.VIBRATE, "strength": 5, "duration_s": 5, **kwargs}
    with pytest.raises(ValidationError, match=match):
        ToyCommand(**base)


def test_rule_carries_modes_through_to_command():
    rule = TipRule(
        name="combo",
        min_sats=1000,
        action=Action.VIBRATE,
        strength=8,
        duration_s=10,
        extra_actions=[{"action": "Rotate", "strength": 4}],
        stop_previous=False,
    )
    cmd = rule.to_command()
    assert cmd.extra_actions[0].action is Action.ROTATE
    assert cmd.stop_previous is False
