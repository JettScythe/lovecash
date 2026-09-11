"""CashToken parsing: CHIP-2022-02 test vectors + synthetic txs."""

import pytest

from lovecash.bch.cashaddr import to_script
from lovecash.bch.tokens import (
    TokenParseError,
    parse_output_payload,
    parse_tx,
)

CAT = "bb" * 32


def _cs(n: int) -> bytes:
    """Minimal CompactSize."""
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + n.to_bytes(2, "little")
    if n <= 0xFFFFFFFF:
        return b"\xfe" + n.to_bytes(4, "little")
    return b"\xff" + n.to_bytes(8, "little")


def _payload(hexstr: str) -> bytes:
    return bytes.fromhex(hexstr)


# --- prefix vectors from the CHIP spec ---


def test_ft_only_1():
    token, script = parse_output_payload(_payload(f"ef{CAT}1001"))
    assert token is not None
    assert token.category == CAT
    assert token.amount == 1
    assert token.nft_capability is None
    assert token.commitment == b""
    assert script == b""


def test_ft_max_vm_number():
    token, _ = parse_output_payload(_payload(f"ef{CAT}10ffffffffffffffff7f"))
    assert token is not None
    assert token.amount == 9223372036854775807


def test_immutable_nft_with_commitment():
    token, _ = parse_output_payload(_payload(f"ef{CAT}6001cc"))
    assert token is not None
    assert token.nft_capability == "none"
    assert token.commitment == b"\xcc"
    assert token.amount == 0


def test_mutable_nft_with_ft_amount():
    # 1-byte mutable NFT + 4294967296 FT
    token, _ = parse_output_payload(_payload(f"ef{CAT}7101ccff0000000001000000"))
    assert token is not None
    assert token.nft_capability == "mutable"
    assert token.commitment == b"\xcc"
    assert token.amount == 4294967296


def test_minting_nft_40byte_commitment():
    token, _ = parse_output_payload(_payload(f"ef{CAT}7228" + "cc" * 40 + "01"))
    assert token is not None
    assert token.nft_capability == "minting"
    assert token.commitment == b"\xcc" * 40
    assert token.amount == 1


def test_payload_after_prefix_is_script():
    token, script = parse_output_payload(_payload(f"ef{CAT}1001") + b"\x51")
    assert token is not None
    assert script == b"\x51"


def test_no_prefix_passes_through():
    token, script = parse_output_payload(b"\x76\xa9\x14" + b"\x00" * 20 + b"\x88\xac")
    assert token is None
    assert script.startswith(b"\x76\xa9")


def test_category_display_byte_order():
    # Prefix stores category in OP_HASH256 byte order; display reverses.
    raw_cat = bytes(range(32)).hex()
    token, _ = parse_output_payload(_payload(f"ef{raw_cat}1001"))
    assert token is not None
    assert token.category == bytes(range(32))[::-1].hex()


@pytest.mark.parametrize(
    "hexstr",
    [
        f"ef{CAT}00",  # encodes no tokens
        f"ef{CAT}5001",  # commitment length without NFT
        f"ef{CAT}23",  # unknown capability 3
        f"ef{CAT}1000",  # zero FT amount
        f"ef{CAT}90" + "01",  # reserved bit set
        f"ef{CAT}60fdfd00" + "cc" * 253,  # commitment > 40 bytes
        f"ef{CAT}10",  # missing amount
        "ef",  # no category
    ],
)
def test_invalid_prefixes_raise(hexstr):
    with pytest.raises(TokenParseError):
        parse_output_payload(_payload(hexstr))


# --- full transaction parsing ---


def _p2pkh(h160: bytes) -> bytes:
    return b"\x76\xa9\x14" + h160 + b"\x88\xac"


def _tx_hex(outputs: list[tuple[int, bytes]]) -> str:
    """Build a minimal tx: 1 dummy input, given (value, payload) outputs."""
    tx = (2).to_bytes(4, "little")
    tx += _cs(1)  # 1 input
    tx += b"\x00" * 32 + (0).to_bytes(4, "little")  # prevout
    tx += _cs(0)  # empty scriptSig
    tx += b"\xff" * 4  # sequence
    tx += _cs(len(outputs))
    for value, payload in outputs:
        tx += value.to_bytes(8, "little")
        tx += _cs(len(payload)) + payload
    tx += (0).to_bytes(4, "little")  # locktime
    return tx.hex()


def test_parse_tx_with_token_output():
    h160 = b"\x11" * 20
    token_payload = _payload(f"ef{CAT}1001") + _p2pkh(h160)
    raw = _tx_hex([(546, token_payload), (1000, _p2pkh(b"\x22" * 20))])
    outs = parse_tx(bytes.fromhex(raw))
    assert len(outs) == 2
    assert outs[0].value_sats == 546
    assert outs[0].token is not None
    assert outs[0].token.amount == 1
    assert outs[0].script == _p2pkh(h160)
    assert outs[1].token is None
    assert outs[1].value_sats == 1000


def test_parse_tx_rejects_garbage():
    with pytest.raises(TokenParseError):
        parse_tx(b"\x02\x00")


def test_token_prefix_script_matches_cashaddr_to_script():
    """The parser's stripped script must match to_script() output — this
    is what lets the watcher match token outputs to our addresses."""
    from lovecash.bch.cashaddr import encode_p2pkh

    pubkey = "02" + "ab" * 32
    addr = encode_p2pkh(pubkey)
    token_addr = encode_p2pkh(pubkey, token_aware=True)
    assert to_script(addr) == to_script(token_addr)  # same script, both kinds
