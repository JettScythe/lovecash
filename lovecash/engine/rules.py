import logging

from lovecash.models import EventRule, TipRule, TokenRule, ToyCommand, ToyEventKind

log = logging.getLogger("lovecash.rules")


class RulesEngine:
    def __init__(
        self,
        rules: list[TipRule],
        token_rules: list[TokenRule] | None = None,
        event_rules: list[EventRule] | None = None,
    ) -> None:
        self._rules = sorted(rules, key=lambda r: r.min_sats, reverse=True)
        self._token_rules = sorted(
            token_rules or [], key=lambda r: r.min_amount, reverse=True
        )
        self._event_rules = sorted(
            event_rules or [], key=lambda r: r.min_value, reverse=True
        )
        # Rising-edge state per (rule index, source toy): was the last
        # value from that toy inside this rule's band? A rebuild of the
        # engine (set_rules) resets edges — every rule may fire once on
        # the next in-band event.
        self._event_edge: dict[tuple[int, str], bool] = {}

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
            for tr in self._token_rules:
                if not tr.matches(receipt):
                    continue
                tcur = best_token.get(tr.toy)
                if tcur is None or tr.min_amount > tcur.min_amount:
                    best_token[tr.toy] = tr
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

    def resolve_event(self, event) -> list[tuple[ToyCommand, str | None]]:
        """Best-matching event rule PER target toy. Shake/button rules
        fire per matching event; depth/motion rules fire on the RISING
        EDGE into their band (value must leave the band before the rule
        can fire again — a sweeping sensor doesn't spam commands)."""
        best: dict[str | None, EventRule] = {}
        for i, r in enumerate(self._event_rules):
            if r.event is not event.event:
                continue
            if r.source_toy is not None and event.toy_id != r.source_toy:
                continue
            if r.button_index is not None and event.button_index != r.button_index:
                continue
            if r.event in (ToyEventKind.SHAKE, ToyEventKind.BUTTON_PRESSED):
                fires = True
            else:
                in_band = (
                    event.value is not None
                    and r.min_value <= event.value <= r.max_value
                )
                key = (i, event.toy_id)
                fires = in_band and not self._event_edge.get(key, False)
                self._event_edge[key] = in_band
            if not fires:
                continue
            cur = best.get(r.toy)
            if cur is None or r.min_value > cur.min_value:
                best[r.toy] = r
        out = [(r.to_command(), r.toy) for r in best.values()]
        if out:
            log.info(
                "Toy event %s from %s matched %d rule(s)",
                event.event.value,
                event.toy_id,
                len(out),
            )
        return out
