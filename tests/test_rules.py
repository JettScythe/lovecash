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
