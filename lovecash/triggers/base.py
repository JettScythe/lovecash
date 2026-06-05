from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from lovecash.triggers.events import TriggerEvent

# Deliberately minimal. A source runs until cancelled and calls emit
# for each event. That's the whole contract.


EmitFn = Callable[[TriggerEvent], Awaitable[None]]


class TriggerSource(ABC):
    @property
    @abstractmethod
    def source_id(self) -> str: ...

    @abstractmethod
    async def run(self, emit: EmitFn) -> None:
        """Run until cancelled, calling emit(event) per trigger."""

    async def close(self) -> None:
        """Optional cleanup on shutdown."""
        return None
