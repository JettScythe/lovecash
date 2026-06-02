from lovecash.models import Action
from lovecash.triggers.events import PaymentTrigger


def _pay(sats: int, conf: int = 1) -> PaymentTrigger:
    return PaymentTrigger(
        source_id="test", txid="t", amount_sats=sats, confirmations=conf
    )


async def test_tip_triggers_command(orch_and_ctrl):
    orch, ctrl = orch_and_ctrl
    orch.router.start()
    await orch._handle_event(_pay(5000))
    assert len(ctrl.commands) == 1
    assert ctrl.commands[0].strength == 4


async def test_unmatched_tip_does_nothing(orch_and_ctrl):
    orch, ctrl = orch_and_ctrl
    orch.router.start()
    await orch._handle_event(_pay(10))
    assert ctrl.commands == []


async def test_high_tier_requires_confirmation(orch_and_ctrl):
    orch, ctrl = orch_and_ctrl
    orch.router.start()
    await orch._handle_event(_pay(60000, conf=0))
    assert ctrl.commands == []
    await orch._handle_event(_pay(60000, conf=1))
    assert ctrl.commands[-1].action == Action.VIBRATE


async def test_observer_error_does_not_break_core(orch_and_ctrl):
    orch, ctrl = orch_and_ctrl
    orch.router.start()

    async def bad_observer(_event) -> None:
        raise RuntimeError("overlay crashed")

    orch.add_observer(bad_observer)
    await orch._handle_event(_pay(5000))
    assert len(ctrl.commands) == 1  # toy still fired despite the crash
