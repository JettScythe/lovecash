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


def _convertbits(data, frm: int, to: int, pad: bool = True) -> list[int]:
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
    if pad and bits:
        out.append((acc << (to - bits)) & maxv)
    return out


def _hash160(data: bytes) -> bytes:
    sha = hashlib.sha256(data).digest()
    return hashlib.new("ripemd160", sha).digest()


# --- decode ---


_SIZE_BITS = {0: 20, 1: 24, 2: 28, 3: 32}


def decode(address: str) -> tuple[int, bytes]:
    """Return (kind, payload_hash). kind 0 = P2PKH, 1 = P2SH,
    2 = P2PKH token-aware, 3 = P2SH token-aware (CHIP-2022-02).
    Hash length comes from the version's size bits: 20 bytes for P2PKH
    and P2SH20, 32 bytes for P2SH32 (covenants)."""
    if ":" in address:
        prefix, payload = address.lower().split(":", 1)
    else:
        prefix, payload = "bitcoincash", address.lower()

    if any(c not in _CHARMAP for c in payload):
        raise ValueError("Invalid CashAddr character")

    data = [_CHARMAP[c] for c in payload]
    if _polymod(_prefix_expand(prefix) + data) != 0:
        raise ValueError("Invalid CashAddr checksum")

    payload_bytes = bytes(_convertbits(data[:-8], 5, 8, pad=False))
    version = payload_bytes[0]
    kind = (version >> 3) & 0x1F
    size = _SIZE_BITS.get(version & 0x07)
    if size is None:
        raise ValueError(f"Invalid CashAddr size bits in version {version:#x}")
    h = payload_bytes[1 : 1 + size]
    if len(h) != size:
        raise ValueError("CashAddr payload truncated")
    if kind in (0, 2) and size != 20:
        raise ValueError(f"P2PKH must be 20 bytes, got {size}")
    return kind, h


def token_variant(address: str) -> str:
    """Return the token-aware (kind 2) form of a P2PKH address.

    Same hash, same script, same scripthash — the `z…` spelling just
    tells wallets they may attach CashTokens to the output."""
    if ":" in address:
        prefix, _ = address.lower().split(":", 1)
    else:
        prefix = "bitcoincash"
    kind, h160 = decode(address)
    if kind == 2:
        return address.lower()
    if kind != 0:
        raise ValueError(f"Cannot make a token-aware variant of kind {kind}")
    return _encode(h160, version=0x10, prefix=prefix)


# --- encode ---


def _encode(h160: bytes, version: int, prefix: str = "bitcoincash") -> str:
    payload = bytes([version]) + h160
    data = _convertbits(payload, 8, 5, pad=True)
    checksum_input = _prefix_expand(prefix) + data + [0] * 8
    polymod = _polymod(checksum_input)
    checksum = [(polymod >> 5 * (7 - i)) & 0x1F for i in range(8)]
    body = "".join(_CHARSET[d] for d in data + checksum)
    return f"{prefix}:{body}"


def encode_p2pkh(
    pubkey_hex: str, prefix: str = "bitcoincash", token_aware: bool = False
) -> str:
    """CashAddr-encode a P2PKH address from a compressed public key."""
    h160 = _hash160(bytes.fromhex(pubkey_hex))
    # version 0x00 = P2PKH, 0x10 = P2PKH token-aware (kind 2), both 160-bit
    return _encode(h160, version=0x10 if token_aware else 0x00, prefix=prefix)


# --- scripthash (for Electrum subscriptions) ---


def to_script(address: str) -> bytes:
    """Locking bytecode (scriptPubKey) for an address. Token-aware kinds
    2/3 share the scripts of kinds 0/1."""
    kind, h = decode(address)
    if kind in (0, 2):
        return b"\x76\xa9\x14" + h + b"\x88\xac"
    if kind in (1, 3):
        return b"\xa9" + bytes([len(h)]) + h + b"\x87"  # P2SH20 / P2SH32
    raise ValueError(f"Unsupported address kind {kind}")


def to_scripthash(address: str) -> str:
    """Electrum scripthash: sha256(scriptPubKey), byte-reversed, hex."""
    return hashlib.sha256(to_script(address)).digest()[::-1].hex()
