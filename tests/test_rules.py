from lovecash.engine.rules import RulesEngine
from lovecash.models import Action, TipEvent, TipRule


def _tip(sats: int, conf: int = 1) -> TipEvent:
    return TipEvent(txid="x", amount_sats=sats, confirmations=conf)


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
    cmd = engine.resolve(_tip(5000))
    assert cmd is not None
    assert cmd.strength == 15
