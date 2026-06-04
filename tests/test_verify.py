import asyncio

from lovecash.bch.verify import Outcome, Verifier

_P2PKH_HEX = "41" + "ab" * 64 + "41" + "21" + "02" + "cd" * 32


def _tx(confirmations=0):
    return {
        "vin": [{"txid": "parent", "scriptSig": {"hex": _P2PKH_HEX}}],
        "confirmations": confirmations,
    }


class FakeWatcher:
    """Models ElectrumClient's dsproof event registry + push."""

    def __init__(self) -> None:
        self.events: dict[str, asyncio.Event] = {}
        self.subscribed: list[str] = []

    def watch(self, txid: str) -> asyncio.Event:
        ev = asyncio.Event()
        self.events[txid] = ev
        return ev

    def unwatch(self, txid: str) -> None:
        self.events.pop(txid, None)

    async def subscribe(self, txid: str):
        self.subscribed.append(txid)
        return None

    def push_proof(self, txid: str) -> None:
        if txid in self.events:
            self.events[txid].set()


async def _fetch_confirmed(txid):
    return _tx(confirmations=5)


async def _no_proof(txid):
    return None


def _verifier(w: FakeWatcher, dsproof_get=_no_proof, window=0.2):
    return Verifier(
        _fetch_confirmed,
        dsproof_get,
        w.watch,
        w.unwatch,
        w.subscribe,
        window_seconds=window,
    )


async def test_protected_clean_window_credits():
    w = FakeWatcher()
    assert await _verifier(w).verify("abc", _tx()) is Outcome.CREDIT


async def test_proof_pushed_during_window_needs_conf():
    w = FakeWatcher()
    v = _verifier(w, window=2.0)
    task = asyncio.create_task(v.verify("abc", _tx()))
    await asyncio.sleep(0.1)  # let it subscribe + open window
    w.push_proof("abc")  # proof arrives via push
    assert await task is Outcome.NEEDS_CONF


async def test_preexisting_proof_needs_conf():
    w = FakeWatcher()

    async def has_proof(txid):
        return {"dspid": "x"}

    assert (
        await _verifier(w, dsproof_get=has_proof).verify("abc", _tx())
        is Outcome.NEEDS_CONF
    )


async def test_unprotected_skips_window_needs_conf():
    w = FakeWatcher()

    async def fetch_p2sh(txid):
        return {
            "vin": [{"txid": "g", "scriptSig": {"hex": "00" + "ab" * 70}}],
            "confirmations": 0,
        }

    v = Verifier(
        fetch_p2sh, _no_proof, w.watch, w.unwatch, w.subscribe, window_seconds=10
    )
    result = await asyncio.wait_for(v.verify("abc", _tx()), timeout=1)
    assert result is Outcome.NEEDS_CONF


async def test_subscribe_failure_needs_conf():
    w = FakeWatcher()

    async def boom(txid):
        raise ConnectionError("down")

    v = Verifier(
        _fetch_confirmed, _no_proof, w.watch, w.unwatch, boom, window_seconds=0.2
    )
    assert await v.verify("abc", _tx()) is Outcome.NEEDS_CONF


async def test_unwatch_always_called():
    w = FakeWatcher()
    await _verifier(w).verify("abc", _tx())
    assert "abc" not in w.events  # cleaned up after credit
