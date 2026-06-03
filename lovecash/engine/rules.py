import logging

from lovecash.models import TipRule, ToyCommand

log = logging.getLogger("lovecash.rules")


class RulesEngine:
    def __init__(self, rules: list[TipRule]) -> None:
        self._rules = sorted(rules, key=lambda r: r.min_sats, reverse=True)

    def resolve_all(self, event) -> list[tuple[ToyCommand, str | None]]:
        """Best-matching rule PER toy target. Rules with toy=None apply
        to all toys. Highest tier wins within each target."""
        best: dict[str | None, TipRule] = {}
        for r in self._rules:
            if not r.matches(event):
                continue
            cur = best.get(r.toy)
            if cur is None or r.min_sats > cur.min_sats:
                best[r.toy] = r
        out = [(r.to_command(), r.toy) for r in best.values()]
        if out:
            log.info("Tip %d sats matched %d rule(s)", event.amount_sats, len(out))
        return out

    # Keep single-result resolve for any legacy callers/tests.
    def resolve(self, event) -> ToyCommand | None:
        results = self.resolve_all(event)
        return results[0][0] if results else None
