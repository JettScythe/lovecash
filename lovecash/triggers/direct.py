import asyncio

from lovecash.models import ToyCommand
from lovecash.triggers.base import EmitFn, TriggerSource
from lovecash.triggers.events import DirectTrigger, ToyTarget


class DirectControlSource(TriggerSource):
    """Partner-driven control. No payment, no rules — direct commands.

    A relay WebSocket endpoint calls push() when the partner sends an
    action. The command still flows through the receiver's safety gate
    and hard limits at the controller, so the receiver stays in control.
    """

    def __init__(self, source_id: str = "partner") -> None:
        self._id = source_id
        self._queue: asyncio.Queue[DirectTrigger] = asyncio.Queue()

    @property
    def source_id(self) -> str:
        return self._id

    async def push(
        self,
        command: ToyCommand,
        actor: str | None = None,
        target: ToyTarget | None = None,
    ) -> None:
        await self._queue.put(
            DirectTrigger(
                source_id=self._id,
                command=command,
                actor=actor,
                target=target or ToyTarget(),
            )
        )

    async def run(self, emit: EmitFn) -> None:
        while True:
            await emit(await self._queue.get())
