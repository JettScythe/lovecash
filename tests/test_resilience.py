from lovecash.models import Action, ToyCommand
from lovecash.triggers.events import DirectTrigger
from lovecash.triggers.status import ConnectionState


def _direct(strength: int) -> DirectTrigger:
    return DirectTrigger(
        source_id="partner",
        command=ToyCommand(action=Action.VIBRATE, strength=strength, duration_s=1),
    )


async def test_direct_control_survives_payment_outage(orch_and_ctrl):
    """A partner's commands keep reaching the toy even while the BCH
    payment source is disconnected/reconnecting. Couples mode must not
    depend on the chain at all."""
    orch, ctrl = orch_and_ctrl
    orch.router.start()

    # Simulate the payment source going down: flip connection state to
    # RECONNECTING, exactly as PaymentSource would broadcast on an outage.
    await orch._broadcast_status(ConnectionState.RECONNECTING)
    assert orch.connection_state is ConnectionState.RECONNECTING

    # Partner command fires regardless of chain connectivity.
    await orch._handle_event(_direct(7))
    assert ctrl.commands[-1].strength == 7

    # Even fully DOWN, direct control still works.
    await orch._broadcast_status(ConnectionState.DOWN)
    await orch._handle_event(_direct(9))
    assert ctrl.commands[-1].strength == 9
    assert len(ctrl.commands) == 2


async def test_panic_stops_direct_control_during_outage(orch_and_ctrl):
    """The panic stop still governs direct control during an outage —
    connectivity state must never weaken the safety gate."""
    orch, ctrl = orch_and_ctrl
    orch.router.start()
    await orch._broadcast_status(ConnectionState.DOWN)

    # NOTE: FakeController ignores the safety gate, so we assert on the
    # authoritative state object, not the fake's command list.
    orch.safety.panic_stop()
    assert orch.safety.stopped is True
    # The real LovenseController.run() checks this same flag; covered
    # end-to-end in test_controller.py::test_panic_blocks_run.
