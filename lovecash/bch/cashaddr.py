import hashlib

_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_CHARMAP = {c: i for i, c in enumerate(_CHARSET)}


def _polymod(values: list[int]) -> int:
    gen = [0x98F2BC8E61, 0x79B76D99E2, 0xF33E5FB3C4, 0xAE2EABE2A8, 0x1E4F43E470]
    chk = 1
    for v in values:
        top = chk >> 35
        chk = ((chk & 0x07FFFFFFFF) << 5) ^ v
        for i in range(5):
            if (top >> i) & 1:
                chk ^= gen[i]
    return chk ^ 1


def _prefix_expand(prefix: str) -> list[int]:
    return [ord(c) & 0x1F for c in prefix] + [0]


def _convertbits(data: list[int], frm: int, to: int) -> list[int]:
    acc = 0
    bits = 0
    out: list[int] = []
    maxv = (1 << to) - 1
    for value in data:
        acc = (acc << frm) | value
        bits += frm
        while bits >= to:
            bits -= to
            out.append((acc >> bits) & maxv)
    return out


def decode(address: str) -> tuple[int, bytes]:
    """Return (version_type, hash160) for a CashAddr.

    version_type 0 = P2PKH, 1 = P2SH.
    """
    if ":" in address:
        prefix, payload = address.lower().split(":", 1)
    else:
        prefix, payload = "bitcoincash", address.lower()

    if any(c not in _CHARMAP for c in payload):
        raise ValueError("Invalid CashAddr character")

    data = [_CHARMAP[c] for c in payload]
    if _polymod(_prefix_expand(prefix) + data) != 0:
        raise ValueError("Invalid CashAddr checksum")

    payload_bytes = bytes(_convertbits(data[:-8], 5, 8))
    version = payload_bytes[0]
    kind = (version >> 3) & 0x1F
    return kind, payload_bytes[1:21]


def to_scripthash(address: str) -> str:
    """Electrum scripthash: sha256(scriptPubKey), byte-reversed, hex."""
    kind, h160 = decode(address)
    if kind == 0:  # P2PKH
        script = b"\x76\xa9\x14" + h160 + b"\x88\xac"
    elif kind == 1:  # P2SH
        script = b"\xa9\x14" + h160 + b"\x87"
    else:
        raise ValueError(f"Unsupported address kind {kind}")
    digest = hashlib.sha256(script).digest()
    return digest[::-1].hex()
