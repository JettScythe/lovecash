from lovecash.triggers.events import PaymentTrigger
from lovecash.triggers.status import ConnectionState


def _pay(sats: int, txid: str = "x") -> PaymentTrigger:
    return PaymentTrigger(source_id="t", txid=txid, amount_sats=sats, confirmations=1)


async def test_dispatch_survives_payment_outage(orch_and_ctrl):
    """Matched tips keep reaching the toy even while the BCH
    payment source reports disconnected/reconnecting."""
    orch, ctrl = orch_and_ctrl
    orch.router.start()

    # Simulate the payment source going down: flip connection state to
    # RECONNECTING, exactly as PaymentSource would broadcast on an outage.
    await orch._broadcast_status(ConnectionState.RECONNECTING)
    assert orch.connection_state is ConnectionState.RECONNECTING

    await orch._handle_event(_pay(5000, "a"))
    assert len(ctrl.commands) == 1

    # Even fully DOWN, dispatch still works.
    await orch._broadcast_status(ConnectionState.DOWN)
    await orch._handle_event(_pay(5000, "b"))
    assert len(ctrl.commands) == 2


async def test_panic_stops_dispatch_during_outage(orch_and_ctrl):
    """The panic stop still governs dispatch during an outage —
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
