"""CashToken (CHIP-2022-02) parsing: token prefixes and raw tx outputs.

Read-only observer code: a parse failure never touches the sats money
path — callers treat it as "no tokens seen" and log.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PREFIX_TOKEN = 0xEF

_CAPABILITY: dict[int, Literal["none", "mutable", "minting"]] = {
    0: "none",
    1: "mutable",
    2: "minting",
}


class TokenParseError(ValueError):
    pass


@dataclass
class TokenData:
    category: str  # 64-hex, display (big-endian) byte order
    amount: int = 0  # fungible base units
    nft_capability: Literal["none", "mutable", "minting"] | None = None
    commitment: bytes = b""


@dataclass
class TxOutput:
    value_sats: int
    token: TokenData | None
    script: bytes  # locking bytecode, token prefix stripped


def _read_compactsize(buf: bytes, off: int) -> tuple[int, int]:
    """Non-strict CompactSize reader (observer only — nodes enforce
    minimal encoding on the token prefix itself)."""
    if off >= len(buf):
        raise TokenParseError("truncated compactsize")
    first = buf[off]
    if first < 0xFD:
        return first, off + 1
    if first == 0xFD:
        size = 2
    elif first == 0xFE:
        size = 4
    else:
        size = 8
    end = off + 1 + size
    if end > len(buf):
        raise TokenParseError("truncated compactsize")
    return int.from_bytes(buf[off + 1 : end], "little"), end


def parse_output_payload(payload: bytes) -> tuple[TokenData | None, bytes]:
    """Split an output's payload into (token data, locking bytecode).

    `payload` is the bytes covered by the output's
    token_prefix_and_locking_bytecode_length field.
    """
    if not payload or payload[0] != PREFIX_TOKEN:
        return None, payload
    if len(payload) < 34:
        raise TokenParseError("token prefix truncated")
    category = payload[1:33][::-1].hex()  # to display byte order
    bitfield = payload[33]
    if bitfield & 0x80:
        raise TokenParseError("reserved bit set")
    has_commitment = bool(bitfield & 0x40)
    has_nft = bool(bitfield & 0x20)
    has_amount = bool(bitfield & 0x10)
    capability = bitfield & 0x0F
    if not has_nft and not has_amount:
        raise TokenParseError("prefix encodes no tokens")
    if has_commitment and not has_nft:
        raise TokenParseError("commitment length without NFT")
    if not has_nft and capability != 0:
        raise TokenParseError("capability without NFT")
    if has_nft and capability > 2:
        raise TokenParseError(f"unknown capability {capability}")

    off = 34
    commitment = b""
    if has_commitment:
        clen, off = _read_compactsize(payload, off)
        if clen < 1 or clen > 40:  # 40 is the consensus cap
            raise TokenParseError(f"invalid commitment length {clen}")
        commitment = payload[off : off + clen]
        if len(commitment) != clen:
            raise TokenParseError("truncated commitment")
        off += clen
    amount = 0
    if has_amount:
        amount, off = _read_compactsize(payload, off)
        if amount < 1:
            raise TokenParseError("zero token amount")

    token = TokenData(
        category=category,
        amount=amount,
        nft_capability=_CAPABILITY[capability] if has_nft else None,
        commitment=commitment,
    )
    return token, payload[off:]


def parse_tx(raw: bytes) -> list[TxOutput]:
    """Parse a raw BCH transaction, returning its outputs.

    BCH has no segwit marker/flag; the format is version, inputs,
    outputs, locktime. Locktime is not needed and not parsed.
    """
    if len(raw) < 10:
        raise TokenParseError("tx too short")
    off = 4  # version
    n_in, off = _read_compactsize(raw, off)
    for _ in range(n_in):
        off += 36  # prevout hash (32) + index (4)
        slen, off = _read_compactsize(raw, off)
        off += slen + 4  # unlocking bytecode + sequence
        if off > len(raw):
            raise TokenParseError("truncated input")
    n_out, off = _read_compactsize(raw, off)
    outputs: list[TxOutput] = []
    for _ in range(n_out):
        if off + 8 > len(raw):
            raise TokenParseError("truncated output value")
        value = int.from_bytes(raw[off : off + 8], "little")
        off += 8
        plen, off = _read_compactsize(raw, off)
        payload = raw[off : off + plen]
        if len(payload) != plen:
            raise TokenParseError("truncated output payload")
        off += plen
        token, script = parse_output_payload(payload)
        outputs.append(TxOutput(value_sats=value, token=token, script=script))
    return outputs
