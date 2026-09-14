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


def test_sum_to_us_counts_token_aware_spelling():
    """Fulcrum may report token outputs under the z… spelling; the sats
    must still count."""
    from lovecash.bch.cashaddr import token_variant

    src = _setup(conf=1, require_conf=True)
    d = XpubDeriver(XPUB)
    src._sh_to_index = {d.scripthash(0): 0}
    z_addr = token_variant(d.address(0))
    tx = {"vout": [{"value": 0.00012345, "scriptPubKey": {"address": z_addr}}]}
    sats, _ = src._sum_to_us(tx)
    assert sats == 12345


async def test_raw_fetch_failure_degrades_to_no_tokens():
    """Transport failure of the raw-hex fetch must not touch the sats
    path: receipts degrade to [], the tip still credits."""

    class FailingClient:
        async def call(self, method, *params, timeout=30):  # noqa: ASYNC109
            raise ConnectionError("fulcrum down")

    src = _setup(conf=1, require_conf=True)
    assert await src._token_receipts(FailingClient(), "tx1") == []


# --- Phase 3: goal-show pot watching ---

POT_ADDR = "bchtest:r0a7vksz5vwdmeqg669u70e7mndfr6ns2ep0vpre4046repxc254jlm500tcr"


class PotFakeClient:
    def __init__(self) -> None:
        self.disconnected = asyncio.Event()
        self.subscribed: set[str] = set()
        self._notify: asyncio.Queue = asyncio.Queue()

    async def connect(self): ...
    async def close(self):
        self.disconnected.set()

    async def subscribe_scripthash(self, sh):
        self.subscribed.add(sh)

    async def call(self, method, *params, timeout=30):  # noqa: ASYNC109
        if method.endswith("get_history"):
            return []
        if method.endswith("get_balance"):
            return {"confirmed": 40_000, "unconfirmed": 5_000}
        return None

    def push_scripthash(self, sh: str):
        self._notify.put_nowait(
            {"method": "blockchain.scripthash.subscribe", "params": [sh, "x"]}
        )

    async def next_notification(self):
        return await self._notify.get()


async def test_pot_subscribed_and_balance_reported():
    from lovecash.config import GoalShowConfig

    client = PotFakeClient()
    balances: list[int] = []

    async def on_pot(b, active):
        assert active is False  # PotFakeClient listunspent returns nothing
        balances.append(b)

    src = PaymentSource(
        _cfg(),
        client_factory=lambda *a: client,
        goal_show=GoalShowConfig(address=POT_ADDR, goal_sats=100_000, deadline=900_000),
        on_pot_balance=on_pot,
    )
    src._client = client
    await src._subscribe_all()

    from lovecash.bch.cashaddr import to_scripthash

    pot_sh = to_scripthash(POT_ADDR)
    assert pot_sh in client.subscribed
    assert pot_sh not in src._sh_to_index  # never enters the tip pipeline
    assert balances == [45_000]  # confirmed + unconfirmed


async def test_pot_notification_updates_balance_not_tips():
    from lovecash.bch.cashaddr import to_scripthash
    from lovecash.config import GoalShowConfig

    client = PotFakeClient()
    balances: list[int] = []
    fired: list = []

    async def on_pot(b, active):
        balances.append(b)

    async def emit(ev):
        fired.append(ev)

    src = PaymentSource(
        _cfg(),
        client_factory=lambda *a: client,
        goal_show=GoalShowConfig(address=POT_ADDR, goal_sats=100_000, deadline=900_000),
        on_pot_balance=on_pot,
    )
    src._client = client
    pot_sh = to_scripthash(POT_ADDR)
    await src._handle_notification(
        {"method": "blockchain.scripthash.subscribe", "params": [pot_sh, "x"]},
        emit,
    )
    assert balances == [45_000]
    assert fired == []


def test_goal_show_config_validates():
    import pytest

    from lovecash.config import GoalShowConfig

    cfg = GoalShowConfig(address=POT_ADDR, goal_sats=100_000, deadline=900_000)
    assert cfg.goal_sats == 100_000
    with pytest.raises(ValueError):
        GoalShowConfig(address=POT_ADDR, goal_sats=0, deadline=900_000)


# --- goal-show UTXO accessors (viewer pledge flow) ---


def _raw_tx_nft(addr: str, category: str, capability: int) -> str:
    """Output paying `addr` carrying an NFT (no commitment/amount)."""
    cat_bytes = bytes.fromhex(category)[::-1]
    prefix = b"\xef" + cat_bytes + bytes([0x20 | capability])
    payload = prefix + to_script(addr)
    tx = (2).to_bytes(4, "little")
    tx += _cs(1) + b"\x00" * 32 + (0).to_bytes(4, "little")
    tx += _cs(0) + b"\xff" * 4
    tx += _cs(1)
    tx += (5000).to_bytes(8, "little") + _cs(len(payload)) + payload
    tx += (0).to_bytes(4, "little")
    return tx.hex()


class UtxoFakeClient(PotFakeClient):
    """Pre-CashToken server: rejects the include_tokens filter param."""

    def __init__(self, rows: list[dict], raws: dict[str, str]) -> None:
        super().__init__()
        self._rows = rows
        self._raws = raws

    async def call(self, method, *params, timeout=30):  # noqa: ASYNC109
        if method.endswith("listunspent"):
            if len(params) > 1:
                raise RuntimeError("too many params")  # no token extension
            return list(self._rows)
        if method.endswith("transaction.get"):
            return self._raws[params[0]]
        return await super().call(method, *params)


async def test_pot_utxo_picks_minting_nft():
    from lovecash.config import GoalShowConfig

    raw_minting = _raw_tx_nft(POT_ADDR, CAT, 2)
    raw_immutable = _raw_tx_nft(POT_ADDR, CAT, 0)
    rows = [
        {"tx_hash": "aa", "tx_pos": 0, "height": 1, "value": 5000},
        {"tx_hash": "bb", "tx_pos": 0, "height": 1, "value": 5000},
    ]
    raws = {"aa": raw_immutable, "bb": raw_minting}
    client = UtxoFakeClient(rows, raws)
    src = PaymentSource(
        _cfg(),
        client_factory=lambda *a: client,
        goal_show=GoalShowConfig(
            address=POT_ADDR,
            goal_sats=100_000,
            deadline=900_000,
            performer_pkh="11" * 20,
        ),
    )
    src._client = client
    pot = await src.pot_utxo()
    assert pot is not None
    assert pot["tx_hash"] == "bb"  # the minting one, not "aa"
    assert pot["token"]["category"] == CAT
    assert pot["token"]["nft"]["capability"] == "minting"
    assert pot["value"] == 5000


async def test_address_utxos_marks_tokenless():
    d = XpubDeriver(XPUB)
    addr = d.address(0)
    rows = [{"tx_hash": "cc", "tx_pos": 0, "height": 1, "value": 546}]
    raws = {"cc": _raw_tx(addr, CAT, 150)}  # token-carrying
    client = UtxoFakeClient(rows, raws)
    src = PaymentSource(_cfg(), client_factory=lambda *a: client)
    src._client = client
    utxos = await src.address_utxos(addr)
    assert len(utxos) == 1
    assert utxos[0]["token"]["amount"] == 150
    # sanity: scripthash lookup used the same address encoding
    from lovecash.bch.cashaddr import to_scripthash

    assert to_scripthash(addr)


async def test_listunspent_prefers_fulcrum_token_extension():
    """Fulcrum hides token UTXOs unless include_tokens is passed — the
    pot carries an NFT, so a plain call reads empty. The extension path
    must be used when available, with fallback when not."""

    class ExtClient(PotFakeClient):
        async def call(self, method, *params, timeout=30):  # noqa: ASYNC109
            if method.endswith("listunspent"):
                if len(params) > 1 and params[1] == "include_tokens":
                    return [
                        {
                            "height": 1,
                            "tx_hash": "aa",
                            "tx_pos": 0,
                            "value": 5000,
                            "token_data": {
                                "amount": "0",
                                "category": CAT,
                                "nft": {"capability": "minting", "commitment": ""},
                            },
                        }
                    ]
                return []  # plain call hides token outputs (Fulcrum behavior)
            return await super().call(method, *params)

    from lovecash.config import GoalShowConfig

    src = PaymentSource(
        _cfg(),
        client_factory=lambda *a: ExtClient(),
        goal_show=GoalShowConfig(
            address=POT_ADDR, goal_sats=100_000, deadline=900_000,
        ),
    )
    src._client = ExtClient()
    pot = await src.pot_utxo()
    assert pot is not None, "token-bearing pot invisible without include_tokens"
    assert pot["token"]["nft"]["capability"] == "minting"


async def test_listunspent_fallback_without_extension():
    """Servers without the CashToken extension: plain listunspent +
    raw-tx parse still finds the pot."""

    class OldClient(PotFakeClient):
        async def call(self, method, *params, timeout=30):  # noqa: ASYNC109
            if method.endswith("listunspent"):
                if len(params) > 1:
                    raise RuntimeError("unknown param")
                return [{"tx_hash": "bb", "tx_pos": 0, "height": 1, "value": 5000}]
            if method.endswith("transaction.get"):
                return _raw_tx_nft(POT_ADDR, CAT, 2)
            return await super().call(method, *params)

    from lovecash.config import GoalShowConfig

    src = PaymentSource(
        _cfg(),
        client_factory=lambda *a: OldClient(),
        goal_show=GoalShowConfig(
            address=POT_ADDR, goal_sats=100_000, deadline=900_000,
        ),
    )
    src._client = OldClient()
    pot = await src.pot_utxo()
    assert pot is not None
    assert pot["token"]["category"] == CAT
