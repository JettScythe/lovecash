import pytest

from lovecash.config import Limits, LovenseConfig
from lovecash.lovense.controller import LovenseController
from lovecash.models import Action, ToyCommand
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
def controller():
    safety = SafetyState(min_interval_s=0)
    ctrl = LovenseController(
        LovenseConfig(),
        Limits(max_strength=10, max_duration_s=5),
        safety,
    )
    ctrl._client = FakeHttp()
    return ctrl, safety


async def test_clamps_to_limits(controller):
    ctrl, _ = controller
    ok = await ctrl.run(ToyCommand(action=Action.VIBRATE, strength=20, duration_s=600))
    assert ok is True
    sent = ctrl._client.posts[0]
    assert sent["action"] == "Vibrate:10"  # strength clamped 20 -> 10
    assert sent["timeSec"] == 5  # duration clamped 600 -> 5


async def test_panic_blocks_run(controller):
    ctrl, safety = controller
    safety.panic_stop()
    ok = await ctrl.run(ToyCommand(action=Action.VIBRATE, strength=5, duration_s=2))
    assert ok is False
    assert ctrl._client.posts == []  # nothing ever sent


async def test_stop_all_always_sends(controller):
    ctrl, safety = controller
    safety.panic_stop()
    await ctrl.stop_all()  # stop bypasses the gate
    assert ctrl._client.posts[-1]["action"] == "Stop"
