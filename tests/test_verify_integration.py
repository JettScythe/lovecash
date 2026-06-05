import asyncio

from lovecash.bch.derive import XpubDeriver
from lovecash.bch.verify import Outcome
from lovecash.config import BchConfig
from lovecash.triggers.payment import PaymentSource

XPUB = (
    "xpub6DF5GApwf8FAAoTTwY6Gk2ZXC1uM6kCqqZBBTEC2Bc6ELxQn6ftHxexXxr8"
    "RsQpka7racgE7QbVs4JBdCXn7XL63LEF8tAC6u6KrT5eeseS"
)


def _vout(addr: str, sats: int) -> dict:
    return {"value": sats / 1e8, "scriptPubKey": {"address": addr}}


def _tx(addr: str, sats: int, conf: int = 0) -> dict:
    return {"vout": [_vout(addr, sats)], "confirmations": conf}


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


def _cfg(**over):
    base = {
        "xpub": XPUB,
        "gap_limit": 5,
        "dsproof_enabled": True,
        "zeroconf_max_sats": 100_000,
        "always_confirm_above_sats": 1_000_000,
    }
    base.update(over)
    return BchConfig(**base)  # type: ignore[arg-type]


async def test_small_tip_skips_verification():
    d = XpubDeriver(XPUB)
    sh = d.scripthash(0)
    client = FakeClient({}, {})
    vcalls: list[str] = []
    fired = []
    src = PaymentSource(
        _cfg(),
        client_factory=lambda *a: client,
        verifier_factory=lambda: StubVerifier(Outcome.CREDIT, vcalls),
    )

    async def emit(ev):
        fired.append(ev)

    t = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.05)
    client._history[sh] = [{"tx_hash": "small", "height": 0}]
    client._txs["small"] = _tx(d.address(0), 4000)  # below threshold
    client.push()
    await asyncio.sleep(0.05)
    assert [f.txid for f in fired] == ["small"]
    assert vcalls == []  # verifier never called
    t.cancel()


async def test_high_value_credit_emits():
    d = XpubDeriver(XPUB)
    sh = d.scripthash(0)
    client = FakeClient({}, {})
    vcalls: list[str] = []
    fired = []
    src = PaymentSource(
        _cfg(),
        client_factory=lambda *a: client,
        verifier_factory=lambda: StubVerifier(Outcome.CREDIT, vcalls),
    )

    async def emit(ev):
        fired.append(ev)

    t = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.05)
    client._history[sh] = [{"tx_hash": "big", "height": 0}]
    client._txs["big"] = _tx(d.address(0), 500_000)  # above threshold
    client.push()
    await asyncio.sleep(0.1)
    assert [f.txid for f in fired] == ["big"]
    assert vcalls == ["big"]  # went through verify
    assert "big" in src._seen
    t.cancel()


async def test_high_value_needs_conf_does_not_emit_or_see():
    d = XpubDeriver(XPUB)
    sh = d.scripthash(0)
    client = FakeClient({}, {})
    vcalls: list[str] = []
    fired = []
    src = PaymentSource(
        _cfg(),
        client_factory=lambda *a: client,
        verifier_factory=lambda: StubVerifier(Outcome.NEEDS_CONF, vcalls),
    )

    async def emit(ev):
        fired.append(ev)

    t = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.05)
    client._history[sh] = [{"tx_hash": "ds", "height": 0}]
    client._txs["ds"] = _tx(d.address(0), 500_000)
    client.push()
    await asyncio.sleep(0.1)
    assert fired == []  # NOT emitted
    assert "ds" not in src._seen  # NOT seen -> re-checked when confirmed
    t.cancel()

    # Now it confirms: re-scan must emit via the confirmed path.
    client._txs["ds"] = _tx(d.address(0), 500_000, conf=1)
    client._history[sh] = [{"tx_hash": "ds", "height": 900000}]
    t2 = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.1)
    # _primed is True so it scans; confirmed tip credits.
    assert [f.txid for f in fired] == ["ds"]
    t2.cancel()


async def test_no_double_spawn_while_verifying():
    d = XpubDeriver(XPUB)
    sh = d.scripthash(0)
    client = FakeClient({}, {})
    vcalls = []

    class SlowVerifier:
        async def verify(self, txid, tx):
            vcalls.append(txid)
            await asyncio.sleep(0.2)
            return Outcome.CREDIT

    src = PaymentSource(
        _cfg(),
        client_factory=lambda *a: client,
        verifier_factory=lambda: SlowVerifier(),
    )

    async def emit(ev): ...

    t = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.05)
    client._history[sh] = [{"tx_hash": "big", "height": 0}]
    client._txs["big"] = _tx(d.address(0), 500_000)
    client.push()
    await asyncio.sleep(0.02)
    client.push()
    await asyncio.sleep(0.02)  # second scan mid-verify
    await asyncio.sleep(0.3)
    assert vcalls == ["big"]  # verified ONCE, not twice
    t.cancel()


# tests/test_verify_integration.py — add
async def test_very_high_value_always_confirms_even_clean():
    """Above the ceiling, wait for a block even with no double-spend.

    A tip over always_confirm_above_sats must never enter verification —
    it waits for a real confirmation regardless of DSProof, because at high
    value, proof-based protection is not sufficient on its own.
    """
    d = XpubDeriver(XPUB)
    sh = d.scripthash(0)
    client = FakeClient({}, {})
    fired: list = []
    vcalls: list[str] = []
    src = PaymentSource(
        _cfg(always_confirm_above_sats=1_000_000),
        client_factory=lambda *a: client,
        verifier_factory=lambda: StubVerifier(Outcome.CREDIT, vcalls),
    )

    async def emit(ev):
        fired.append(ev)

    t = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.05)

    # 2M sats: above the 1M ceiling. Stubbed verifier would CREDIT if asked,
    # so this proves the ceiling short-circuits BEFORE verification.
    client._history[sh] = [{"tx_hash": "huge", "height": 0}]
    client._txs["huge"] = _tx(d.address(0), 2_000_000)
    client.push()
    await asyncio.sleep(0.1)

    assert fired == []  # NOT emitted
    assert vcalls == []  # verifier NEVER consulted
    assert "huge" not in src._seen  # un-seen -> credited when confirmed
    t.cancel()
