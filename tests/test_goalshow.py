"""GoalShow auto-claim: the Python claim builder is byte-identical to
cashscript's TransactionBuilder output (golden fixture generated via
contracts/node_modules), and the watcher broadcasts it when the pot
reaches the goal."""

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
    "52d100886875516868feffffff0108460200000000001976a914"
    "1111111111111111111111111111111111111111" "88ac00000000"
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
    src._client = client
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
