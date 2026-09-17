"""GoalShow auto-claim: the Python claim builder is byte-identical to
cashscript's TransactionBuilder output (fixture cross-checked against
cashscript-py 1.0.3 on 2026-09-13), and the watcher broadcasts it when
the pot reaches the goal. The claim fee is exact (tx size at 1 sat/byte),
well under the covenant's 1000-sat cap."""

import asyncio

from lovecash.bch.goalshow import build_claim_tx
from lovecash.config import BchConfig, GoalShowConfig
from lovecash.triggers.payment import PaymentSource

PKH = "11" * 20
GOAL = 100_000
DEADLINE = 900_000
CAT_DISPLAY = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
POT_ADDR = "bchtest:r0wujj4094cfd8y64chw8e0me9wj847th4fd3ewynjxn3et6fc54wl0gvqh76"
XPUB = "xpub6DF5GApwf8FAAoTTwY6Gk2ZXC1uM6kCqqZBBTEC2Bc6ELxQn6ftHxexXxr8RsQpka7racgE7QbVs4JBdCXn7XL63LEF8tAC6u6KrT5eeseS"

GOLDEN_CLAIM = (
    "0200000001aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    "01000000fd9801514d9401201f1e1d1c1b1a191817161514131211100f0e0d0c0b0a0908"
    "070605040302010003a0bb0d03a08601141111111111111111111111111111111111111111"
    "5479009c63557a82011488c5b175c0009dc3529dc5547a9f6900ce76827701219d7601207f"
    "7752887601207f7555798800cc00c69476028813a26900cd00c78800d17b8800d200cf8851"
    "cd0376a91453797e0288ac7e8851d1557a8851d27b7b58807e88c453a169c4539c6352d100"
    "88686d7551675479519c63c0009dc3519d00ce76827701219d7601207f77528801207f7554"
    "7a8800c67ba269c4519d00cd0376a9147b7e0288ac7e8800cc00c602e80394a26900d10087"
    "777767547a529dc0009dc3529d7bb17500c67b9f6900ce76827701219d7601207f77528876"
    "01207f7553798851ce537a8851cf768277011c9d01147f76577f7701808401008881760222"
    "02a2697600c6a16900cc00c6527994a26900cd00c78800d1537a8800d200cf8851cd0376a9"
    "14537a7e0288ac7e8851cc022202a26951cc7c02e80394a26951d10088c453a169c4539c63"
    "52d100886875516868feffffff0101480200000000001976a914"
    "1111111111111111111111111111111111111111"
    "88ac00000000"
)


def test_claim_tx_matches_cashscript_golden():
    hex_tx = build_claim_tx(
        pot_txid="aa" * 32,
        pot_vout=1,
        pot_sats=150_000,
        performer_pkh=bytes.fromhex(PKH),
        goal_sats=GOAL,
        deadline=DEADLINE,
        category_raw=bytes.fromhex(CAT_DISPLAY)[::-1],
        pot_address=POT_ADDR,
    )
    assert hex_tx == GOLDEN_CLAIM


def test_claim_tx_refuses_mismatched_pot_address():
    import pytest

    with pytest.raises(ValueError, match="does not match"):
        build_claim_tx(
            pot_txid="aa" * 32,
            pot_vout=1,
            pot_sats=150_000,
            performer_pkh=bytes.fromhex("22" * 20),  # not the address's pkh
            goal_sats=GOAL,
            deadline=DEADLINE,
            category_raw=bytes.fromhex(CAT_DISPLAY)[::-1],
            pot_address=POT_ADDR,
        )


class ClaimFakeClient:
    def __init__(self, pot_value: int) -> None:
        self.disconnected = asyncio.Event()
        self.broadcasts: list[str] = []
        self._pot_value = pot_value

    async def connect(self): ...
    async def subscribe_scripthash(self, sh): ...
    async def close(self):
        self.disconnected.set()

    async def call(self, method, *params, timeout=30):  # noqa: ASYNC109
        if method.endswith("listunspent"):
            return [
                {
                    "tx_hash": "aa" * 32,
                    "tx_pos": 1,
                    "height": 100,
                    "value": self._pot_value,
                    "token_data": {
                        "category": CAT_DISPLAY,
                        "amount": "0",
                        "nft": {"capability": "minting", "commitment": ""},
                    },
                }
            ]
        if method.endswith("transaction.broadcast"):
            self.broadcasts.append(params[0])
            return "bb" * 32
        return None

    async def next_notification(self):
        return await asyncio.Event().wait()


def _src(pot_value: int, performer_pkh: str = PKH) -> PaymentSource:
    client = ClaimFakeClient(pot_value)
    src = PaymentSource(
        BchConfig(xpub=XPUB),
        client_factory=lambda *a: client,
        goal_show=GoalShowConfig(
            address=POT_ADDR,
            goal_sats=GOAL,
            deadline=DEADLINE,
            performer_pkh=performer_pkh,
        ),
    )
    src._client = client  # type: ignore[assignment]
    return src


async def test_auto_claim_broadcasts_when_goal_met():
    src = _src(pot_value=150_000)
    await src._maybe_auto_claim(150_000)
    assert src._client.broadcasts == [GOLDEN_CLAIM]

    # Same pot outpoint is not retried.
    await src._maybe_auto_claim(150_000)
    assert len(src._client.broadcasts) == 1


async def test_auto_claim_noop_below_goal():
    src = _src(pot_value=90_000)
    await src._maybe_auto_claim(90_000)
    assert src._client.broadcasts == []


async def test_auto_claim_needs_performer_pkh():
    src = _src(pot_value=150_000, performer_pkh="")
    await src._maybe_auto_claim(150_000)
    assert src._client.broadcasts == []


# --- genesis verification (performer wallet-signed deploy) ---


def _locking(
    pkh: str = PKH, goal: int = GOAL, deadline: int = DEADLINE, cat: str = CAT_DISPLAY
) -> bytes:
    from lovecash.bch.goalshow import _p2sh32_locking, redeem_script

    return _p2sh32_locking(
        redeem_script(bytes.fromhex(pkh), goal, deadline, bytes.fromhex(cat)[::-1])
    )


def _token_payload(
    script: bytes,
    category: str = CAT_DISPLAY,
    bitfield: int = 0x22,
    commitment: bytes = b"",
) -> bytes:
    payload = b"\xef" + bytes.fromhex(category)[::-1] + bytes([bitfield])
    if bitfield & 0x40:
        payload += bytes([len(commitment)]) + commitment
    return payload + script


def _genesis_hex(
    token_payloads: list[bytes],
    input0_category: str = CAT_DISPLAY,
    seed: int = 5000,
    vout: int = 0,
) -> str:
    """One-tx genesis+seed: input 0's outpoint txid IS the category."""
    tx = bytearray()
    tx += (2).to_bytes(4, "little")  # version
    tx += b"\x01"  # one input
    tx += bytes.fromhex(input0_category)[::-1]
    tx += vout.to_bytes(4, "little")
    tx += b"\x00"  # empty scriptSig (the node already checked the signature)
    tx += b"\xff\xff\xff\xff"
    tx += bytes([1 + len(token_payloads)])
    change = b"\x76\xa9\x14" + bytes.fromhex(PKH) + b"\x88\xac"
    tx += (9000).to_bytes(8, "little") + bytes([len(change)]) + change
    for payload in token_payloads:
        tx += seed.to_bytes(8, "little") + bytes([len(payload)]) + payload
    tx += (0).to_bytes(4, "little")  # locktime
    return tx.hex()


def test_verify_genesis_tx_valid():
    from lovecash.bch.goalshow import verify_genesis_tx

    info = verify_genesis_tx(
        _genesis_hex([_token_payload(_locking())]),
        bytes.fromhex(PKH),
        GOAL,
        DEADLINE,
        POT_ADDR,
    )
    assert info == {"category": CAT_DISPLAY, "seed_sats": 5000}


def test_verify_genesis_tx_rejects_wrong_constructor():
    import pytest

    from lovecash.bch.goalshow import verify_genesis_tx

    with pytest.raises(ValueError, match="not locked to this show's covenant"):
        verify_genesis_tx(
            _genesis_hex([_token_payload(_locking())]),
            bytes.fromhex("22" * 20),  # not the deployer's pkh
            GOAL,
            DEADLINE,
            POT_ADDR,
        )


def test_verify_genesis_tx_rejects_split_mint():
    import pytest

    from lovecash.bch.goalshow import verify_genesis_tx

    # A second token output = the mint-then-seed forgery window.
    with pytest.raises(ValueError, match="exactly one token output"):
        verify_genesis_tx(
            _genesis_hex(
                [
                    _token_payload(_locking()),
                    _token_payload(b"\x76\xa9\x14" + bytes.fromhex(PKH) + b"\x88\xac"),
                ]
            ),
            bytes.fromhex(PKH),
            GOAL,
            DEADLINE,
            POT_ADDR,
        )


def test_verify_genesis_tx_rejects_committed_nft():
    import pytest

    from lovecash.bch.goalshow import verify_genesis_tx

    with pytest.raises(ValueError, match="not a bare minting NFT"):
        verify_genesis_tx(
            _genesis_hex(
                [_token_payload(_locking(), bitfield=0x62, commitment=b"\x01" * 4)]
            ),
            bytes.fromhex(PKH),
            GOAL,
            DEADLINE,
            POT_ADDR,
        )


def test_verify_genesis_tx_rejects_category_mismatch():
    import pytest

    from lovecash.bch.goalshow import verify_genesis_tx

    with pytest.raises(ValueError, match="not the genesis category"):
        verify_genesis_tx(
            _genesis_hex([_token_payload(_locking(cat="ff" * 32), category="ff" * 32)]),
            bytes.fromhex(PKH),
            GOAL,
            DEADLINE,
            POT_ADDR,
        )


def test_verify_genesis_tx_rejects_wrong_address():
    import pytest

    from lovecash.bch.cashaddr import _encode
    from lovecash.bch.goalshow import verify_genesis_tx

    wrong = _encode(_locking(goal=GOAL + 1)[2:34], version=0x1B, prefix="bchtest")
    with pytest.raises(ValueError, match="does not match the given pot address"):
        verify_genesis_tx(
            _genesis_hex([_token_payload(_locking())]),
            bytes.fromhex(PKH),
            GOAL,
            DEADLINE,
            wrong,
        )


def test_verify_genesis_tx_rejects_nonzero_outpoint_index():
    """CHIP-2022-02: only outpoint index 0 can create a category — the
    chipnet rejection that gate-tested the wallet deploy flow."""
    import pytest

    from lovecash.bch.goalshow import verify_genesis_tx

    with pytest.raises(ValueError, match="output index 0"):
        verify_genesis_tx(
            _genesis_hex([_token_payload(_locking())], vout=2),
            bytes.fromhex(PKH),
            GOAL,
            DEADLINE,
            POT_ADDR,
        )


# --- /api/goal_show endpoint ---


def _deploy_payload(txid: str = "aa" * 32) -> dict:
    return {
        "genesis_txid": txid,
        "goal_sats": GOAL,
        "deadline": DEADLINE,
        "performer_pkh": PKH,
        "address": POT_ADDR,
    }


def _server_client(monkeypatch, raw_hex: str | None, attached: list):
    import asyncio

    import pytest

    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lovecash.config import BchConfig, Limits, LovenseConfig, ServerConfig, Settings
    from lovecash.core.orchestrator import Orchestrator
    from lovecash.server.app import create_app

    async def _noop_run(self):
        await asyncio.Event().wait()

    async def _raw(self, txid):
        return raw_hex

    async def _attach(self, gs):
        attached.append(gs)

    monkeypatch.setattr(Orchestrator, "run", _noop_run)
    monkeypatch.setattr(Orchestrator, "raw_transaction", _raw)
    monkeypatch.setattr(Orchestrator, "attach_goal_show", _attach)
    cfg = Settings(
        limits=Limits(),
        lovense=LovenseConfig(),
        bch=BchConfig(xpub=XPUB),
        server=ServerConfig(),
    )
    return TestClient(create_app(cfg), base_url="http://127.0.0.1:8080")


def test_deploy_endpoint_verifies_attaches_and_reports(monkeypatch):
    attached: list = []
    genesis = _genesis_hex([_token_payload(_locking())])
    with _server_client(monkeypatch, genesis, attached) as client:
        resp = client.post("/api/goal_show", json=_deploy_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] and body["watching"] and not body["needs_restart"]
    assert body["category"] == CAT_DISPLAY and body["seed_sats"] == 5000
    assert not body["persisted"]  # no config_path in tests
    assert len(attached) == 1 and attached[0].address == POT_ADDR


def test_deploy_endpoint_rejects_forged_genesis(monkeypatch):
    attached: list = []
    forged = _genesis_hex(
        [_token_payload(_locking(pkh="22" * 20), category=CAT_DISPLAY)]
    )
    # forged tx locks to the "22" covenant but claims the "11" show's params
    with _server_client(monkeypatch, forged, attached) as client:
        resp = client.post("/api/goal_show", json=_deploy_payload())
    assert resp.status_code == 400
    assert "not locked" in resp.json()["detail"]
    assert attached == []


def test_deploy_endpoint_404_until_tx_visible(monkeypatch):
    attached: list = []
    with _server_client(monkeypatch, None, attached) as client:
        resp = client.post("/api/goal_show", json=_deploy_payload())
    assert resp.status_code == 404
    assert attached == []
