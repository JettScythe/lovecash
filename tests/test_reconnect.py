import asyncio

from lovecash.bch.derive import XpubDeriver
from lovecash.config import BchConfig
from lovecash.triggers.payment import PaymentSource

ADDR = "bitcoincash:qqhx545cwyqvgtre0t2yn8lwzjzajvfaqg87ruq9gw"

XPUB = "xpub6DF5GApwf8FAAoTTwY6Gk2ZXC1uM6kCqqZBBTEC2Bc6ELxQn6ftHxexXxr8RsQpka7racgE7QbVs4JBdCXn7XL63LEF8tAC6u6KrT5eeseS"


class FakeClient:
    """Electrum stand-in keyed by scripthash.

    history: dict[scripthash -> list[{"tx_hash", "height"}]]
    txs:     dict[txid -> verbose tx]
    """

    def __init__(self, history: dict, txs: dict) -> None:
        self.disconnected = asyncio.Event()
        self._history = history
        self._txs = txs
        self._notify: asyncio.Queue = asyncio.Queue()
        self.subscribed: set[str] = set()

    async def connect(self): ...

    async def subscribe_scripthash(self, sh):
        self.subscribed.add(sh)
        # Real Fulcrum sends a notification on subscribe — model it.
        self._notify.put_nowait({"method": "x.subscribe"})

    async def close(self):
        self.disconnected.set()

    async def call(self, method, *params, timeout=30):  # noqa: ASYNC109
        if method.endswith("get_history"):
            sh = params[0]
            return list(self._history.get(sh, []))  # list of dicts
        if method.endswith("transaction.get"):
            return self._txs[params[0]]
        return None

    def push(self):
        self._notify.put_nowait({"method": "x.subscribe"})

    async def next_notification(self):
        return await self._notify.get()


def _tx(value_bch: float, addr: str, conf: int = 1) -> dict:
    return {
        "vout": [{"value": value_bch, "scriptPubKey": {"address": addr}}],
        "confirmations": conf,
    }


async def test_no_double_fire_and_gap_recovery():
    d = XpubDeriver(XPUB)
    history: dict = {}  # empty chain -> discovery lands at index 0
    txs: dict = {}
    client = FakeClient(history, txs)

    fired: list = []

    async def emit(ev):
        fired.append(ev)

    src = PaymentSource(BchConfig(xpub=XPUB), client_factory=lambda *a: client)
    task = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.05)  # discovery: empty chain -> index 0
    assert src._next_index == 0

    # Live tip on the watched index 0 -> fires once.
    sh0 = d.scripthash(0)
    history[sh0] = [{"tx_hash": "live", "height": 101}]
    txs["live"] = _tx(0.00006, d.address(0))
    client.push()
    await asyncio.sleep(0.05)
    assert [f.txid for f in fired] == ["live"]

    # Block re-notification, same tx already seen -> no double fire.
    client.push()
    await asyncio.sleep(0.05)
    assert [f.txid for f in fired] == ["live"]
    task.cancel()


async def test_gap_recovery_after_outage():
    d = XpubDeriver(XPUB)
    history: dict = {}
    txs: dict = {}
    client = FakeClient(history, txs)

    fired: list = []

    async def emit(ev):
        fired.append(ev)

    src = PaymentSource(BchConfig(xpub=XPUB), client_factory=lambda *a: client)

    task = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.05)  # discovery -> index 0
    task.cancel()
    await asyncio.sleep(0.01)

    # Tip arrives during the outage, on the watched index 0.
    sh0 = d.scripthash(0)
    history[sh0] = [{"tx_hash": "gap", "height": 102}]
    txs["gap"] = _tx(0.00007, d.address(0))

    # Reconnect: _primed is True, so _session rescans (not rediscovers),
    # recovering the gap tip.
    task2 = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.05)
    assert [f.txid for f in fired] == ["gap"]
    task2.cancel()
