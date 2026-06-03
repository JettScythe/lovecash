from abc import ABC, abstractmethod

from lovecash.engine.rules import RulesEngine
from lovecash.models import ToyCommand
from lovecash.triggers.events import (
    ToyTarget,
    TriggerEvent,
)


class Resolver(ABC):
    @abstractmethod
    def resolve(self, event: TriggerEvent) -> list[tuple[ToyCommand, ToyTarget]]: ...


class PaymentResolver(Resolver):
    def __init__(self, engine: RulesEngine) -> None:
        self._engine = engine

    def resolve(self, event) -> list[tuple[ToyCommand, ToyTarget]]:
        out = []
        for cmd, toy in self._engine.resolve_all(event):
            target = ToyTarget(toy_ids=[toy] if toy else [])
            out.append((cmd, target))
        return out


class DirectResolver(Resolver):
    def resolve(self, event) -> list[tuple[ToyCommand, ToyTarget]]:
        return [(event.command, event.target)]
