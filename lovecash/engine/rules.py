import logging

from lovecash.models import TipEvent, TipRule, ToyCommand

log = logging.getLogger("lovecash.rules")


class RulesEngine:
    """Resolves a tip into a toy command using performer-authored rules.

    Rules are matched most-specific-first (highest min_sats wins) so that
    larger tips override smaller-tier defaults.
    """

    def __init__(self, rules: list[TipRule]) -> None:
        self._rules = sorted(rules, key=lambda r: r.min_sats, reverse=True)

    def resolve(self, tip: TipEvent) -> ToyCommand | None:
        for rule in self._rules:
            if rule.matches(tip):
                log.info("Tip %d sats matched rule '%s'", tip.amount_sats, rule.name)
                return rule.to_command()
        log.debug("No rule matched tip of %d sats", tip.amount_sats)
        return None
