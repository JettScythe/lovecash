from conftest import FakeController

from lovecash.config import Limits, LovenseConfig, Playback
from lovecash.core.router import ToyRouter
from lovecash.engine.rules import RulesEngine
from lovecash.models import Action, TipRule
from lovecash.safety import SafetyState
from lovecash.triggers.events import PaymentTrigger, ToyTarget

ADDR = "bitcoincash:qqhx545cwyqvgtre0t2yn8lwzjzajvfaqg87ruq9gw"


def _pay(sats):
    return PaymentTrigger(source_id="t", txid="x", amount_sats=sats, confirmations=1)


def test_one_tip_drives_two_toys():
    engine = RulesEngine(
        [
            TipRule(
                name="his",
                min_sats=1000,
                toy="his",
                action=Action.THRUSTING,
                strength=6,
                duration_s=5,
            ),
            TipRule(
                name="hers",
                min_sats=1000,
                toy="hers",
                action=Action.VIBRATE,
                strength=8,
                duration_s=5,
            ),
        ]
    )
    results = engine.resolve_all(_pay(2000))
    targets = {toy for _, toy in results}
    assert targets == {"his", "hers"}


def test_highest_tier_wins_per_toy():
    engine = RulesEngine(
        [
            TipRule(
                name="his-low",
                min_sats=1000,
                toy="his",
                action=Action.THRUSTING,
                strength=4,
                duration_s=3,
            ),
            TipRule(
                name="his-high",
                min_sats=5000,
                toy="his",
                action=Action.THRUSTING,
                strength=12,
                duration_s=10,
            ),
        ]
    )
    results = engine.resolve_all(_pay(6000))
    assert len(results) == 1
    assert results[0][0].strength == 12  # high tier won for "his"


def test_untargeted_rule_hits_all():
    engine = RulesEngine(
        [
            TipRule(
                name="all",
                min_sats=1000,
                action=Action.VIBRATE,
                strength=5,
                duration_s=3,
            ),
        ]
    )
    results = engine.resolve_all(_pay(2000))
    assert results[0][1] is None  # None target = all toys


async def test_router_dispatches_to_named_toy():
    safety = SafetyState(0)
    router = ToyRouter(safety, Limits(playback=Playback.OVERRIDE))
    a, b = FakeController("his"), FakeController("hers")
    router.add_toy("his", a)
    router.add_toy("hers", b)
    router.start()
    from lovecash.models import ToyCommand

    await router.dispatch(
        ToyCommand(action=Action.VIBRATE, strength=5, duration_s=1),
        ToyTarget(toy_ids=["his"]),
    )
    assert len(a.commands) == 1 and len(b.commands) == 0


async def test_panic_stops_all_toys():
    safety = SafetyState(0)
    router = ToyRouter(safety, Limits(playback=Playback.OVERRIDE))
    a, b = FakeController("his"), FakeController("hers")
    router.add_toy("his", a)
    router.add_toy("hers", b)
    # The single shared safety governs both.
    assert router.safety is safety
    safety.panic_stop()
    assert router.safety.stopped is True


def test_legacy_single_toy_config():
    """A config with no `toys` list still yields exactly one toy."""
    cfg = LovenseConfig(toy_id="abc123")
    toys = cfg.resolved_toys()
    assert len(toys) == 1
    assert toys[0].toy_id == "abc123"


def test_legacy_no_toy_id_defaults():
    """No toy_id at all -> one 'default' toy (sole connected device)."""
    cfg = LovenseConfig()
    toys = cfg.resolved_toys()
    assert len(toys) == 1
    assert toys[0].toy_id == "default"


def test_router_from_legacy_settings(settings):
    """from_settings builds one toy from a legacy config."""
    from lovecash.core.router import ToyRouter
    from lovecash.safety import SafetyState

    router = ToyRouter.from_settings(settings, SafetyState(0))
    assert len(router._toys) == 1
