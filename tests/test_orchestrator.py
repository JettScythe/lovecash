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
    # Untargeted rule reached the single toy.
    assert ctrl.toy_id == "default"


async def test_unmatched_tip_does_nothing(orch_and_ctrl):
    orch, ctrl = orch_and_ctrl
    orch.router.start()
    await orch._handle_event(_pay(10))
    assert ctrl.commands == []


async def test_observer_error_does_not_break_core(orch_and_ctrl):
    orch, ctrl = orch_and_ctrl
    orch.router.start()

    async def bad_observer(_event) -> None:
        raise RuntimeError("overlay crashed")

    orch.add_observer(bad_observer)
    await orch._handle_event(_pay(5000))
    assert len(ctrl.commands) == 1  # toy still fired despite the crash


def test_orchestrator_adopts_router_safety(orch_and_ctrl):
    """Panic stop must act on the same SafetyState the toys check."""
    orch, _ = orch_and_ctrl
    assert orch.safety is orch.router.safety
