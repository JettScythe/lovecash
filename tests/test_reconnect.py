import asyncio

from lovecash.config import BchConfig
from lovecash.triggers.payment import PaymentSource

ADDR = "bitcoincash:qpm2qsznhks23z7629mms6s4cwef74vcwvy22gdx6a"


class FakeClient:
    """Scriptable Electrum stand-in. `history` is mutated by tests to
    simulate tips arriving (including during an 'outage')."""

    def __init__(self, history, txs) -> None:
        self.disconnected = asyncio.Event()
        self._history = history
        self._txs = txs
        self._notify = asyncio.Queue()

    async def connect(self): ...
    async def subscribe_scripthash(self, sh): ...
    async def close(self):
        self.disconnected.set()

    async def call(self, method, *params, timeout=30):  # noqa: ASYNC109
        if method.endswith("get_history"):
            return list(self._history)
        if method.endswith("transaction.get"):
            return self._txs[params[0]]
        return None

    def push(self):  # signal a new notification
        self._notify.put_nowait({"method": "x.subscribe"})

    async def next_notification(self):
        return await self._notify.get()


def _tx(addr, sats, conf=1):
    return {
        "vout": [{"value": sats / 1e8, "scriptPubKey": {"address": addr}}],
        "confirmations": conf,
    }


async def test_no_double_fire_and_gap_recovery():
    cfg = BchConfig(address=ADDR)
    history = [{"tx_hash": "old", "height": 100}]
    txs = {"old": _tx(ADDR, 5000), "gap": _tx(ADDR, 7000)}
    client = FakeClient(history, txs)

    fired = []
    src = PaymentSource(cfg, client_factory=lambda *a: client)

    async def emit(ev):
        fired.append(ev.txid)

    # First session: prime swallows "old", so it must NOT fire.
    task = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.05)
    assert fired == []  # priming swallowed history

    # A tip arrives during normal operation.
    history.append({"tx_hash": "live", "height": 101})
    txs["live"] = _tx(ADDR, 6000)
    client.push()
    await asyncio.sleep(0.05)
    assert fired == ["live"]

    # Simulate outage: close client, a tip lands while we're down.
    await client.close()
    task.cancel()
    history.append({"tx_hash": "gap", "height": 102})

    # Reconnect: _primed is now True, so scan fires only the gap tip.
    client2 = FakeClient(history, txs)
    src._client_factory = lambda *a: client2
    task2 = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.05)
    assert "gap" in fired  # gap recovered
    assert fired.count("old") == 0  # never re-fired
    task2.cancel()
