import asyncio

from lovecash.config import BchConfig, PricingConfig
from lovecash.triggers.payment import PaymentSource

XPUB = (
    "xpub6DF5GApwf8FAAoTTwY6Gk2ZXC1uM6kCqqZBBTEC2Bc6ELxQn6ftHxexXxr8"
    "RsQpka7racgE7QbVs4JBdCXn7XL63LEF8tAC6u6KrT5eeseS"
)


def _vout(addr: str, sats: int) -> dict:
    return {"value": sats / 1e8, "scriptPubKey": {"address": addr}}


def _tx(addr: str, sats: int, conf: int = 0) -> dict:
    return {"vout": [_vout(addr, sats)], "confirmations": conf}


# (reuse FakeClient + StubVerifier + _tx/_vout from test_verify_integration)
class FakeClient:
    def __init__(self, history, txs):
        self.disconnected = asyncio.Event()
        self._history = history
        self._txs = txs
        self._notify: asyncio.Queue = asyncio.Queue()
        self.subscribed: set[str] = set()

    async def connect(self): ...
    async def subscribe_scripthash(self, sh):
        self.subscribed.add(sh)
        self._notify.put_nowait({"method": "x.subscribe"})

    async def close(self):
        self.disconnected.set()

    async def call(self, method, *params, timeout=30):  # noqa: ASYNC109
        if method.endswith("get_history"):
            return list(self._history.get(params[0], []))
        if method.endswith("transaction.get"):
            return self._txs[params[0]]
        return None

    def push(self):
        self._notify.put_nowait({"method": "x.subscribe"})

    async def next_notification(self):
        return await self._notify.get()

    def drain_notifications(self):
        while not self._notify.empty():
            self._notify.get_nowait()


class StubVerifier:
    def __init__(self, outcome, calls):
        self._o = outcome
        self._calls = calls

    async def verify(self, txid, tx):
        self._calls.append(txid)
        return self._o


def test_ceiling_uses_sats_net_when_pricing_disabled():
    cfg = BchConfig(xpub=XPUB, always_confirm_above_sats=5_000_000)
    src = PaymentSource(cfg)
    assert src._effective_ceiling_sats() == 5_000_000


def test_ceiling_falls_back_to_sats_when_price_unavailable():
    """Pricing enabled but oracle never refreshed -> sats net, NOT a
    loosened ceiling. This is the safety-critical fallback."""
    cfg = BchConfig(
        xpub=XPUB,
        always_confirm_above_sats=5_000_000,
        pricing=PricingConfig(enabled=True, always_confirm_above_usd=50),
    )
    src = PaymentSource(cfg)
    # feed exists but has no price (never refreshed) -> usd_to_sats None
    assert src._price_feed is not None
    assert src._price_feed.usd_to_sats(50) is None
    assert src._effective_ceiling_sats() == 5_000_000  # safe fallback


def test_both_ceilings_lower_wins():
    """Both ceilings active; the tighter (in sats) wins. At $215/BCH,
    1 BCH (100M sats) is tighter than $500 (~232M sats), so 1 BCH wins."""
    import time

    cfg = BchConfig(
        xpub=XPUB,
        always_confirm_above_sats=100_000_000,  # 1 BCH
        pricing=PricingConfig(enabled=True, always_confirm_above_usd=500),
    )
    src = PaymentSource(cfg)
    assert src._price_feed is not None
    src._price_feed._price = 215.0
    src._price_feed._fetched_at = time.monotonic()
    # $500/$215*1e8 = ~232M sats; min(232M, 100M) = 100M (1 BCH wins)
    assert src._effective_ceiling_sats() == 100_000_000


def test_usd_wins_when_price_high():
    """If BCH is expensive enough, $500 maps to fewer sats than 1 BCH,
    so the USD ceiling becomes the tighter one and wins."""
    import time

    cfg = BchConfig(
        xpub=XPUB,
        always_confirm_above_sats=100_000_000,  # 1 BCH
        pricing=PricingConfig(enabled=True, always_confirm_above_usd=500),
    )
    src = PaymentSource(cfg)
    assert src._price_feed is not None
    src._price_feed._price = 1000.0  # at $1000/BCH, $500 = 0.5 BCH = 50M sats
    src._price_feed._fetched_at = time.monotonic()
    assert src._effective_ceiling_sats() == 50_000_000  # USD wins, tighter


def test_oracle_never_loosens_past_sats_net():
    """Even a (wrong) price mapping to MORE sats than the net cannot raise
    the ceiling above the hardcoded safety net."""
    import time

    cfg = BchConfig(
        xpub=XPUB,
        always_confirm_above_sats=1_000_000,  # low net
        pricing=PricingConfig(enabled=True, always_confirm_above_usd=50),
    )
    src = PaymentSource(cfg)
    assert src._price_feed is not None
    src._price_feed._price = 5.0  # absurdly low -> $50 = 1B sats
    src._price_feed._fetched_at = time.monotonic()
    # min(1B, 1M) == 1M: the net wins, oracle cannot loosen.
    assert src._effective_ceiling_sats() == 1_000_000
