"""End-to-end: a CashToken tip is detected from raw tx hex, gated by
require_conf, and lands on the trigger with receipts attached."""

import asyncio

from lovecash.bch.cashaddr import to_script
from lovecash.bch.derive import XpubDeriver
from lovecash.config import BchConfig
from lovecash.models import Action, TokenRule
from lovecash.triggers.payment import PaymentSource

XPUB = "xpub6DF5GApwf8FAAoTTwY6Gk2ZXC1uM6kCqqZBBTEC2Bc6ELxQn6ftHxexXxr8RsQpka7racgE7QbVs4JBdCXn7XL63LEF8tAC6u6KrT5eeseS"
CAT = "bb" * 32


def _cs(n: int) -> bytes:
    if n < 0xFD:
        return bytes([n])
    return b"\xfd" + n.to_bytes(2, "little")


def _raw_tx(addr: str, category: str, amount: int) -> str:
    """Token output paying `addr`: dust value + FT prefix."""
    # category arg is display-order hex; the prefix stores it reversed
    cat_bytes = bytes.fromhex(category)[::-1]
    prefix = b"\xef" + cat_bytes + b"\x10" + _cs(amount)
    payload = prefix + to_script(addr)
    tx = (2).to_bytes(4, "little")
    tx += _cs(1) + b"\x00" * 32 + (0).to_bytes(4, "little")
    tx += _cs(0) + b"\xff" * 4
    tx += _cs(1)
    tx += (546).to_bytes(8, "little") + _cs(len(payload)) + payload
    tx += (0).to_bytes(4, "little")
    return tx.hex()


class FakeClient:
    def __init__(self, history: dict, txs: dict, raws: dict) -> None:
        self.disconnected = asyncio.Event()
        self._history = history
        self._txs = txs
        self._raws = raws
        self._notify: asyncio.Queue = asyncio.Queue()

    async def connect(self): ...
    async def subscribe_scripthash(self, sh): ...
    async def close(self):
        self.disconnected.set()

    async def call(self, method, *params, timeout=30):  # noqa: ASYNC109
        if method.endswith("get_history"):
            return list(self._history.get(params[0], []))
        if method.endswith("transaction.get"):
            # verbose=True -> decoded dict; default -> raw hex
            if len(params) > 1 and params[1]:
                return self._txs[params[0]]
            return self._raws[params[0]]
        return None

    async def next_notification(self):
        return await self._notify.get()


def _cfg(**over) -> BchConfig:
    base = {
        "xpub": XPUB,
        "gap_limit": 5,
        "rotate_on_payment": False,
        "zeroconf_max_sats": 100_000,
        "always_confirm_above_sats": 1_000_000,
        "dsproof_enabled": False,
    }
    base.update(over)
    return BchConfig(**base)  # type: ignore[arg-type]


def _rule(require_conf: bool) -> list[TokenRule]:
    return [
        TokenRule(
            name="fan",
            category=CAT,
            min_amount=100,
            require_conf=require_conf,
            action=Action.VIBRATE,
            strength=6,
            duration_s=3,
        )
    ]


def _setup(conf: int, require_conf: bool):
    d = XpubDeriver(XPUB)
    addr = d.address(0)
    sh0 = d.scripthash(0)
    history = {sh0: [{"tx_hash": "tx1", "height": 100 if conf else 0}]}
    txs = {
        "tx1": {
            "vout": [{"value": 0.00000546, "scriptPubKey": {"address": addr}}],
            "confirmations": conf,
        }
    }
    raws = {"tx1": _raw_tx(addr, CAT, 150)}
    client = FakeClient(history, txs, raws)
    src = PaymentSource(
        _cfg(), client_factory=lambda *a: client, token_rules=_rule(require_conf)
    )
    return src


async def test_confirmed_token_tip_emits_receipt():
    src = _setup(conf=1, require_conf=True)
    fired: list = []

    async def emit(ev):
        fired.append(ev)

    client = src._client_factory()
    src._client = client
    src._sh_to_index = {XpubDeriver(XPUB).scripthash(0): 0}
    await src._scan_all(emit)
    assert len(fired) == 1
    ev = fired[0]
    assert len(ev.tokens) == 1
    assert ev.tokens[0].category == CAT
    assert ev.tokens[0].amount == 150
    assert ev.amount_sats == 546  # dust rides along


async def test_unconfirmed_require_conf_goes_pending():
    src = _setup(conf=0, require_conf=True)
    fired: list = []
    statuses: list = []

    async def on_tip_status(tip_id, status, extra):
        statuses.append((tip_id, status, extra))

    src._on_tip_status = on_tip_status

    async def emit(ev):
        fired.append(ev)

    src._client = src._client_factory()
    src._sh_to_index = {XpubDeriver(XPUB).scripthash(0): 0}
    await src._scan_all(emit)
    assert fired == []  # nothing fired yet
    assert "tx1" in src._pending_conf
    assert statuses and statuses[0][2].get("reason") == "token_conf"


async def test_unconfirmed_no_require_conf_fires_instantly():
    src = _setup(conf=0, require_conf=False)
    fired: list = []

    async def emit(ev):
        fired.append(ev)

    src._client = src._client_factory()
    src._sh_to_index = {XpubDeriver(XPUB).scripthash(0): 0}
    await src._scan_all(emit)
    assert len(fired) == 1
    assert fired[0].tokens[0].amount == 150


async def test_no_token_rules_means_no_raw_fetch():
    """Without token rules the watcher never fetches raw hex."""
    src = PaymentSource(_cfg(), client_factory=None)
    assert src._token_rules == []

    class CountingClient:
        async def call(self, method, *params, timeout=30):  # noqa: ASYNC109
            raise AssertionError("should not be called without rules")

    assert await src._token_receipts(CountingClient(), "tx1") == []


def test_tip_address_is_token_aware_with_rules():
    src = _setup(conf=1, require_conf=True)
    plain = src.current_address()
    tip = src.current_tip_address()
    assert tip != plain
    from lovecash.bch.cashaddr import decode

    assert decode(tip)[0] == 2
    src2 = PaymentSource(_cfg(), client_factory=None)
    assert src2.current_tip_address() == src2.current_address()
