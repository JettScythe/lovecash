from abc import ABC, abstractmethod

from lovecash.engine.rules import RulesEngine
from lovecash.models import ToyCommand
from lovecash.triggers.events import DirectTrigger, PaymentTrigger, TriggerEvent


class Resolver(ABC):
    @abstractmethod
    def resolve(self, event: TriggerEvent) -> list[ToyCommand]: ...


class PaymentResolver(Resolver):
    def __init__(self, engine: RulesEngine) -> None:
        self._engine = engine

    def resolve(self, event: PaymentTrigger) -> list[ToyCommand]:
        cmd = self._engine.resolve(event)  # uses amount_sats/confirmations
        return [cmd] if cmd else []


class DirectResolver(Resolver):
    def resolve(self, event: DirectTrigger) -> list[ToyCommand]:
        return [event.command]
