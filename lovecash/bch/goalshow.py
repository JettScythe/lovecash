"""GoalShow covenant claim-tx builder (phase 3 auto-claim).

claim() takes no arguments and needs no signatures — anyone can settle a
met goal. The relay builds and broadcasts it the moment the pot reaches
the goal, so the performer is paid automatically without touching a
wallet. The constructed covenant address is verified against the
configured pot address before broadcast: a constructor/config mismatch
produces a tx that could never validate, so we refuse to send it.

Built with cashscript-py from the compiled artifact (goal_show.json,
kept in sync with contracts/goal_show.cash — regenerate with cashc per
contracts/README.md). Byte-identical to cashscript's JS
TransactionBuilder output; tests/test_goalshow.py holds the golden
fixture.
"""

from __future__ import annotations

import json

from pathlib import Path

from cashscript_py import Contract, TransactionBuilder
from cashscript_py.interfaces import NftCapability, Output, TokenDetails, Utxo
from cashscript_py.network.network_provider import Network, NetworkProvider

MAX_CLAIM_FEE_SATS = 1000  # covenant caps the claim fee at 1000 sats

_ARTIFACT = json.loads(Path(__file__).with_name("goal_show.json").read_text())


class _OfflineProvider(NetworkProvider):
    """Build-only provider: constructing/broadcasting goes through the
    watcher's Electrum client; cashscript-py just needs a network for
    address prefixes."""

    def __init__(self, network: Network) -> None:
        self._network = network

    @property
    def network(self) -> Network:
        return self._network

    async def get_utxos(self, address: str) -> list[Utxo]:
        raise NotImplementedError

    async def get_block_height(self) -> int:
        raise NotImplementedError

    async def get_raw_transaction(self, txid: str) -> str:
        raise NotImplementedError

    async def send_raw_transaction(self, tx_hex: str) -> str:
        raise NotImplementedError


def _network_for(pot_address: str) -> Network:
    prefix = pot_address.split(":")[0]
    if prefix == "bitcoincash":
        return Network.MAINNET
    if prefix == "bchtest":  # chipnet and testnet share the prefix
        return Network.CHIPNET
    raise ValueError(f"unrecognized pot address prefix: {prefix}")


def build_claim_tx(
    pot_txid: str,
    pot_vout: int,
    pot_sats: int,
    performer_pkh: bytes,
    goal_sats: int,
    deadline: int,
    category_raw: bytes,
    pot_address: str,
) -> str:
    """Serialize the claim transaction. Raises if the constructed covenant
    address does not match the configured pot address — a mismatched
    config can never produce a valid claim, so refuse early."""
    provider = _OfflineProvider(_network_for(pot_address))
    contract = Contract(
        _ARTIFACT,
        [performer_pkh.hex(), goal_sats, deadline, category_raw.hex()],
        provider,
    )
    if pot_address not in (contract.address, contract.token_address):
        raise ValueError("constructed covenant does not match the configured pot address")
    if pot_sats < goal_sats:
        raise ValueError("goal not met")

    # The pot carries the category's minting NFT (category in display
    # order, as Electrum reports it; raw is the reverse).
    pot = Utxo(
        pot_txid,
        pot_vout,
        pot_sats,
        TokenDetails(
            0,
            category_raw[::-1].hex(),
            TokenDetails.Nft(NftCapability.MINTING, ""),
        ),
    )
    performer_script = b"\x76\xa9\x14" + performer_pkh + b"\x88\xac"  # P2PKH

    def build(fee: int) -> str:
        return (
            TransactionBuilder(provider)
            .add_input(pot, contract.unlock["claim"]())
            .add_output(Output(to=performer_script, amount=pot_sats - fee))
            .build()
        )

    # Exact fee at 1 sat/byte: the tx size doesn't depend on the output
    # amount, so a dry run gives the real size. The covenant caps the fee
    # at 1000 sats — refuse to build a tx it would reject.
    fee = len(build(0)) // 2
    if fee > MAX_CLAIM_FEE_SATS:
        raise ValueError(f"claim fee {fee} exceeds the covenant cap")
    return build(fee)
