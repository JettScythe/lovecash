import asyncio

from lovecash.bch.derive import XpubDeriver
from lovecash.config import BchConfig
from lovecash.triggers.payment import PaymentSource

XPUB = "xpub6DF5GApwf8FAAoTTwY6Gk2ZXC1uM6kCqqZBBTEC2Bc6ELxQn6ftHxexXxr8RsQpka7racgE7QbVs4JBdCXn7XL63LEF8tAC6u6KrT5eeseS"


def _cfg(**over) -> BchConfig:
    base = {"xpub": XPUB, "gap_limit": 5, "rotate_on_payment": True}
    base.update(over)
    return BchConfig(**base)


def _tx(value_bch: float, addr: str, conf: int = 1) -> dict:
    return {
        "vout": [{"value": value_bch, "scriptPubKey": {"address": addr}}],
        "confirmations": conf,
    }


class FakeClient:
    """Scriptable Electrum stand-in keyed by scripthash.

    `history[sh]` is a list of {tx_hash, height}; `txs[txid]` is the
    verbose tx. Tests mutate these to simulate tips arriving, then call
    push() to fire a notification.
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


async def test_window_detects_tip_advances_and_rotates():
    d = XpubDeriver(XPUB)
    sh0 = d.scripthash(0)

    history: dict = {}
    txs: dict = {}
    client = FakeClient(history, txs)

    fired: list = []
    rotations: list = []

    async def emit(ev):
        fired.append(ev)

    async def on_address(addr, index):
        rotations.append((addr, index))

    src = PaymentSource(
        _cfg(),
        on_address=on_address,
        client_factory=lambda *a: client,
    )

    task = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.05)  # let it connect + prime + emit on_address

    # It subscribed to the whole gap-limit window (5 scripthashes).
    assert len(client.subscribed) == 5
    # Priming swallowed nothing (empty history) and fired no tips.
    assert fired == []
    # On connect it announced the current (index 0) address.
    assert rotations[-1] == (d.address(0), 0)

    # A tip lands at index 0.
    history[sh0] = [{"tx_hash": "tip0", "height": 100}]
    txs["tip0"] = _tx(0.00003523, d.address(0))  # 3523 sats
    client.push()
    await asyncio.sleep(0.05)

    # Trigger emitted with the right amount.
    assert len(fired) == 1
    assert fired[0].amount_sats == 3523
    assert fired[0].kind == "payment"

    # next_index advanced past the paid index.
    assert src._next_index == 1
    # Window extended: index 5 (newly exposed) is now subscribed.
    assert d.scripthash(5) in client.subscribed
    # Overlay rotated to index 1.
    assert rotations[-1] == (d.address(1), 1)

    task.cancel()


async def test_no_rotation_when_disabled():
    d = XpubDeriver(XPUB)
    sh0 = d.scripthash(0)
    history = {sh0: []}
    txs = {}
    client = FakeClient(history, txs)
    rotations = []

    async def emit(ev): ...
    async def on_address(addr, index):
        rotations.append(index)

    src = PaymentSource(
        _cfg(rotate_on_payment=False),
        on_address=on_address,
        client_factory=lambda *a: client,
    )
    _task = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.05)

    history[sh0] = [{"tx_hash": "t", "height": 100}]
    txs["t"] = _tx(0.00002000, d.address(0))
    client.push()
    await asyncio.sleep(0.05)

    # Index still advances (we must keep watching ahead)...
    assert src._next_index == 1
    # ...but no NEW rotation event beyond the initial connect announce.
    assert rotations == [0]
