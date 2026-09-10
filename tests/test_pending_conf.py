"""Tips that must wait for a block (high-value, or DSProof refused)
stay watched until they confirm — even after their address rotates out
of the gap-limit window or the Electrum session reconnects."""

import asyncio

from lovecash.bch.derive import XpubDeriver
from lovecash.config import BchConfig
from lovecash.triggers.payment import PaymentSource

XPUB = "xpub6DF5GApwf8FAAoTTwY6Gk2ZXC1uM6kCqqZBBTEC2Bc6ELxQn6ftHxexXxr8RsQpka7racgE7QbVs4JBdCXn7XL63LEF8tAC6u6KrT5eeseS"


def _tx(value_bch: float, addr: str, conf: int = 1) -> dict:
    return {
        "vout": [{"value": value_bch, "scriptPubKey": {"address": addr}}],
        "confirmations": conf,
    }


class FakeClient:
    """Scriptable Electrum stand-in keyed by scripthash."""

    def __init__(self, history: dict, txs: dict) -> None:
        self.disconnected = asyncio.Event()
        self._history: dict = history
        self._txs: dict = txs
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

    def push_scripthash(self, sh: str):
        self._notify.put_nowait(
            {"method": "blockchain.scripthash.subscribe", "params": [sh, "x"]}
        )

    async def next_notification(self):
        return await self._notify.get()


def _cfg(**over) -> BchConfig:
    base = {
        "xpub": XPUB,
        "gap_limit": 5,
        "rotate_on_payment": True,
        "zeroconf_max_sats": 100_000,
        "always_confirm_above_sats": 1_000_000,
        "dsproof_enabled": False,
    }
    base.update(over)
    return BchConfig(**base)  # type: ignore[arg-type]


async def test_pending_tip_survives_rotation_and_reconnect():
    d = XpubDeriver(XPUB)
    sh0 = d.scripthash(0)
    history: dict = {}
    txs: dict = {}
    client = FakeClient(history, txs)
    fired: list = []
    statuses: list = []

    async def emit(ev):
        fired.append(ev)

    async def on_tip_status(tip_id, status, extra):
        statuses.append((tip_id, status))

    src = PaymentSource(
        _cfg(), on_tip_status=on_tip_status, client_factory=lambda *a: client
    )
    task = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.05)

    # A 0-conf tip above the always-confirm ceiling: must wait for a block.
    history[sh0] = [{"tx_hash": "huge", "height": 0}]
    txs["huge"] = _tx(0.006, d.address(0), conf=0)  # 600_000 sats
    client.push()
    await asyncio.sleep(0.05)
    assert fired == []
    assert statuses == [("huge", "confirming")]

    # Six small confirmed tips rotate the window past index 0.
    for n in range(1, 7):
        history[d.scripthash(n)] = [{"tx_hash": f"t{n}", "height": 100 + n}]
        txs[f"t{n}"] = _tx(0.00002, d.address(n))
        client.push()
        await asyncio.sleep(0.02)
    assert src._next_index == 7

    # Reconnect: resubscribe from scratch. The pending tip's address must
    # still be watched even though it is far outside the window.
    client.subscribed.clear()
    await src._subscribe_all()
    assert sh0 in client.subscribed

    # The block lands. A status-change notification on that address...
    history[sh0] = [{"tx_hash": "huge", "height": 200}]
    txs["huge"]["confirmations"] = 1
    client.push_scripthash(sh0)
    await asyncio.sleep(0.05)

    # ...credits the tip instead of losing it.
    assert [f.txid for f in fired if f.txid == "huge"] == ["huge"]
    assert "huge" not in src._pending_conf
    task.cancel()


async def test_confirming_announced_once_not_per_scan():
    d = XpubDeriver(XPUB)
    sh0 = d.scripthash(0)
    history: dict = {}
    txs: dict = {}
    client = FakeClient(history, txs)
    statuses: list = []

    async def emit(ev): ...
    async def on_tip_status(tip_id, status, extra):
        statuses.append((tip_id, status))

    src = PaymentSource(
        _cfg(), on_tip_status=on_tip_status, client_factory=lambda *a: client
    )
    task = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.05)

    history[sh0] = [{"tx_hash": "huge", "height": 0}]
    txs["huge"] = _tx(0.006, d.address(0), conf=0)
    for _ in range(3):  # repeated scans of the same unconfirmed tx
        client.push()
        await asyncio.sleep(0.02)
    assert statuses.count(("huge", "confirming")) == 1
    task.cancel()


async def test_pending_tx_vanishing_stops_the_watch():
    """A pending tx double-spent out of the mempool is dropped, not
    watched forever."""
    d = XpubDeriver(XPUB)
    sh0 = d.scripthash(0)
    history: dict = {}
    txs: dict = {}
    client = FakeClient(history, txs)

    async def emit(ev): ...

    src = PaymentSource(_cfg(), client_factory=lambda *a: client)
    task = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.05)

    history[sh0] = [{"tx_hash": "huge", "height": 0}]
    txs["huge"] = _tx(0.006, d.address(0), conf=0)
    client.push()
    await asyncio.sleep(0.05)
    assert "huge" in src._pending_conf

    history[sh0] = []  # evicted / double-spent away
    client.push_scripthash(sh0)
    await asyncio.sleep(0.05)
    assert "huge" not in src._pending_conf
    task.cancel()


async def test_notification_scans_only_the_notified_address():
    d = XpubDeriver(XPUB)
    sh1 = d.scripthash(1)
    history: dict = {}
    txs: dict = {}
    client = FakeClient(history, txs)
    fired: list = []

    async def emit(ev):
        fired.append(ev)

    src = PaymentSource(_cfg(), client_factory=lambda *a: client)
    task = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.05)  # primed on an empty chain

    calls: list[str] = []
    orig_call = client.call

    async def counting_call(method, *params, timeout=30):  # noqa: ASYNC109
        if method.endswith("get_history"):
            calls.append(params[0])
        return await orig_call(method, *params, timeout=timeout)

    client.call = counting_call  # type: ignore[method-assign]

    # A new confirmed tip at index 1, notified with its scripthash.
    history[sh1] = [{"tx_hash": "c", "height": 101}]
    txs["c"] = _tx(0.00004, d.address(1))
    client.push_scripthash(sh1)
    await asyncio.sleep(0.05)

    assert [f.txid for f in fired] == ["c"]
    assert calls == [sh1]  # no fan-out across the whole window
    task.cancel()
