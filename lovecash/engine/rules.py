import logging

from lovecash.models import TipRule, TokenRule, ToyCommand

log = logging.getLogger("lovecash.rules")


class RulesEngine:
    def __init__(
        self, rules: list[TipRule], token_rules: list[TokenRule] | None = None
    ) -> None:
        self._rules = sorted(rules, key=lambda r: r.min_sats, reverse=True)
        self._token_rules = sorted(
            token_rules or [], key=lambda r: r.min_amount, reverse=True
        )

    def resolve_all(self, event) -> list[tuple[ToyCommand, str | None]]:
        """Best-matching rule PER toy target. Rules with toy=None apply
        to all toys. Highest tier wins within each target. Sats rules and
        token rules resolve independently — a tip carrying both can fire
        one command from each."""
        best: dict[str | None, TipRule] = {}
        for r in self._rules:
            if not r.matches(event):
                continue
            cur = best.get(r.toy)
            if cur is None or r.min_sats > cur.min_sats:
                best[r.toy] = r
        best_token: dict[str | None, TokenRule] = {}
        for receipt in getattr(event, "tokens", []):
            for r in self._token_rules:
                if not r.matches(receipt):
                    continue
                cur = best_token.get(r.toy)
                if cur is None or r.min_amount > cur.min_amount:
                    best_token[r.toy] = r
        out = [(r.to_command(), r.toy) for r in best.values()]
        out += [(r.to_command(), r.toy) for r in best_token.values()]
        if out:
            log.info(
                "Tip %d sats + %d token receipt(s) matched %d rule(s)",
                event.amount_sats,
                len(getattr(event, "tokens", [])),
                len(out),
            )
        return out
