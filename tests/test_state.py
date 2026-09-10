"""Restart behavior: persisted watcher state credits tips that arrived
while offline, never double-fires, and fails safe on a corrupt file."""

import asyncio
from pathlib import Path

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

    async def next_notification(self):
        return await self._notify.get()


def _cfg() -> BchConfig:
    return BchConfig(
        xpub=XPUB,
        gap_limit=5,
        zeroconf_max_sats=100_000,
        always_confirm_above_sats=1_000_000,
        dsproof_enabled=False,
    )


async def _run_session(state_path: Path, client: FakeClient, fired: list) -> None:
    """One lovecash 'session': run until settled, then shut down."""

    async def emit(ev):
        fired.append(ev)

    src = PaymentSource(_cfg(), client_factory=lambda *a: client, state_path=state_path)
    task = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.08)
    task.cancel()
    await src.close()


async def test_first_run_seeds_history_without_firing(tmp_path):
    """No state file = no way to tell missed tips from credited ones.
    Fail safe: mark all current history handled, fire nothing."""
    d = XpubDeriver(XPUB)
    history = {d.scripthash(0): [{"tx_hash": "old", "height": 100}]}
    txs = {"old": _tx(0.00005, d.address(0))}
    fired: list = []
    await _run_session(tmp_path / "state.json", FakeClient(history, txs), fired)
    assert fired == []


async def test_restart_credits_tip_that_arrived_while_offline(tmp_path):
    d = XpubDeriver(XPUB)
    history: dict = {}
    txs: dict = {}
    state = tmp_path / "state.json"

    fired: list = []
    await _run_session(state, FakeClient(history, txs), fired)
    assert fired == [] and state.exists()

    # lovecash was OFF when this tip landed (already 1 confirmation).
    history[d.scripthash(0)] = [{"tx_hash": "offline", "height": 200}]
    txs["offline"] = _tx(0.00005, d.address(0))

    fired2: list = []
    await _run_session(state, FakeClient(history, txs), fired2)
    assert [f.txid for f in fired2] == ["offline"]


async def test_restart_never_double_fires(tmp_path):
    d = XpubDeriver(XPUB)
    sh0 = d.scripthash(0)
    history: dict = {}
    txs: dict = {}
    state = tmp_path / "state.json"

    fired: list = []
    client = FakeClient(history, txs)

    async def emit(ev):
        fired.append(ev)

    src = PaymentSource(_cfg(), client_factory=lambda *a: client, state_path=state)
    task = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.05)
    history[sh0] = [{"tx_hash": "live", "height": 100}]
    txs["live"] = _tx(0.00005, d.address(0))
    client.push()
    await asyncio.sleep(0.05)
    task.cancel()
    await src.close()
    assert [f.txid for f in fired] == ["live"]

    # Same history, new process: nothing may fire again.
    fired2: list = []
    await _run_session(state, FakeClient(history, txs), fired2)
    assert fired2 == []


async def test_corrupt_state_starts_fresh_without_firing(tmp_path):
    d = XpubDeriver(XPUB)
    history = {d.scripthash(0): [{"tx_hash": "old", "height": 100}]}
    txs = {"old": _tx(0.00005, d.address(0))}
    state = tmp_path / "state.json"
    state.write_text("{not json")

    fired: list = []
    await _run_session(state, FakeClient(history, txs), fired)
    assert fired == []  # missed a maybe-missed tip rather than double-fire


async def test_pending_confirmation_survives_restart(tmp_path):
    """High-value 0-conf tip is pending when lovecash stops; it confirms
    while down; the restart credits it (and only then)."""
    d = XpubDeriver(XPUB)
    sh0 = d.scripthash(0)
    history: dict = {}
    txs: dict = {}
    state = tmp_path / "state.json"

    fired: list = []
    client = FakeClient(history, txs)

    async def emit(ev):
        fired.append(ev)

    src = PaymentSource(_cfg(), client_factory=lambda *a: client, state_path=state)
    task = asyncio.create_task(src._session(emit))
    await asyncio.sleep(0.05)
    history[sh0] = [{"tx_hash": "huge", "height": 0}]
    txs["huge"] = _tx(0.006, d.address(0), conf=0)  # 600k sats: wait for block
    client.push()
    await asyncio.sleep(0.05)
    task.cancel()
    await src.close()
    assert fired == []

    # Block lands while lovecash is off; restart credits it.
    history[sh0] = [{"tx_hash": "huge", "height": 300}]
    txs["huge"]["confirmations"] = 1
    fired2: list = []
    await _run_session(state, FakeClient(history, txs), fired2)
    assert [f.txid for f in fired2] == ["huge"]
