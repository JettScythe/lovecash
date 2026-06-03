import asyncio

from lovecash.models import Action, ToyCommand
from lovecash.triggers.direct import DirectControlSource
from lovecash.triggers.events import DirectTrigger


async def test_direct_source_emits_trigger():
    """The source relays a pushed command as a DirectTrigger."""
    src = DirectControlSource("alice")
    got = []

    async def emit(ev):
        got.append(ev)

    task = asyncio.create_task(src.run(emit))
    await src.push(ToyCommand(action=Action.VIBRATE, strength=7, duration_s=1))
    await asyncio.sleep(0.05)
    task.cancel()

    assert got[0].kind == "direct"
    assert got[0].command.strength == 7
    assert got[0].actor is None


async def test_partner_command_reaches_toy(orch_and_ctrl):
    orch, ctrl = orch_and_ctrl
    orch.router.start()
    trig = DirectTrigger(
        source_id="alice",
        command=ToyCommand(action=Action.VIBRATE, strength=5, duration_s=1),
    )
    await orch._handle_event(trig)
    assert ctrl.commands[-1].strength == 5
