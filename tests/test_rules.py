from lovecash.engine.rules import RulesEngine
from lovecash.models import Action, TipRule
from lovecash.triggers.events import PaymentTrigger


def _tip(sats: int, conf: int = 1) -> PaymentTrigger:
    return PaymentTrigger(source_id="t", txid="x", amount_sats=sats, confirmations=conf)


def test_highest_tier_wins():
    engine = RulesEngine(
        [
            TipRule(
                name="low",
                min_sats=0,
                max_sats=999,
                action=Action.VIBRATE,
                strength=3,
                duration_s=2,
            ),
            TipRule(
                name="high",
                min_sats=1000,
                action=Action.VIBRATE,
                strength=15,
                duration_s=10,
            ),
        ]
    )
    results = engine.resolve_all(_tip(5000))
    assert results
    assert results[0][0].strength == 15


# --- CashToken rules ---

CAT = "bb" * 32


def _token_tip(
    sats: int = 546, amount: int = 0, category: str = CAT, conf: int = 1
) -> PaymentTrigger:
    from lovecash.models import TokenReceipt

    receipts = (
        [TokenReceipt(category=category, amount=amount)] if amount else []
    )
    return PaymentTrigger(
        source_id="t", txid="x", amount_sats=sats, confirmations=conf,
        tokens=receipts,
    )


def _token_rule(name, min_amount, **kw):
    from lovecash.models import TokenRule

    return TokenRule(
        name=name,
        category=kw.pop("category", CAT),
        min_amount=min_amount,
        action=Action.VIBRATE,
        strength=kw.pop("strength", 5),
        duration_s=3,
        **kw,
    )


def test_token_rule_matches_by_category_and_range():
    engine = RulesEngine([], [_token_rule("fan", 100, strength=9)])
    assert engine.resolve_all(_token_tip(amount=150))[0][0].strength == 9
    assert engine.resolve_all(_token_tip(amount=50)) == []
    assert engine.resolve_all(_token_tip(amount=150, category="cc" * 32)) == []
    assert engine.resolve_all(_tip(100_000)) == []  # no receipts, no match


def test_token_highest_tier_wins_per_toy():
    engine = RulesEngine(
        [],
        [
            _token_rule("low", 100, strength=4),
            _token_rule("high", 1000, strength=15),
        ],
    )
    results = engine.resolve_all(_token_tip(amount=5000))
    assert len(results) == 1
    assert results[0][0].strength == 15


def test_sats_and_token_rules_both_fire():
    engine = RulesEngine(
        [
            TipRule(
                name="sats", min_sats=0, action=Action.VIBRATE,
                strength=2, duration_s=1,
            )
        ],
        [_token_rule("fan", 100, strength=9)],
    )
    results = engine.resolve_all(_token_tip(amount=150))
    assert {c.strength for c, _ in results} == {2, 9}


def test_token_rule_category_validation():
    import pytest

    from lovecash.models import TokenRule

    with pytest.raises(ValueError):
        TokenRule(
            name="bad", category="not-hex", min_amount=1,
            action=Action.VIBRATE, strength=1, duration_s=1,
        )
    # uppercase normalizes to lowercase
    r = TokenRule(
        name="ok", category=CAT.upper(), min_amount=1,
        action=Action.VIBRATE, strength=1, duration_s=1,
    )
    assert r.category == CAT
    assert r.require_conf is True  # safe default
