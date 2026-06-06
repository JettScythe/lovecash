from collections.abc import Awaitable, Callable
from enum import StrEnum

TxFetcher = Callable[[str], Awaitable[dict]]


class Protection(StrEnum):
    PROTECTED = "protected"  # safe to credit on 0-conf after window
    UNPROTECTED = "unprotected"  # must wait for confirmation
    UNKNOWN = "unknown"  # ambiguous -> treat as unprotected


def _parse_pushes(script_hex: str) -> list[bytes] | None:
    """Parse a scriptSig hex into its pushed items. Returns None if it's
    not a simple sequence of small data pushes (i.e. not standard P2PKH)."""
    try:
        data = bytes.fromhex(script_hex)
    except ValueError:
        return None
    pushes: list[bytes] = []
    i = 0
    n = len(data)
    while i < n:
        op = data[i]
        i += 1
        # Only accept direct data pushes (0x01..0x4b). Anything else
        # (OP_PUSHDATA1+, opcodes, redeem scripts) -> not standard P2PKH.
        if 1 <= op <= 0x4B:
            if i + op > n:
                return None
            pushes.append(data[i : i + op])
            i += op
        else:
            return None
    return pushes


_SIGHASH_ALL = 0x41  # ALL | FORKID (BCH)


def _input_is_standard(vin: dict) -> bool:
    """P2PKH spend signed with SIGHASH_ALL only: scriptSig is exactly
    <sig+sighash> <pubkey>, sighash byte == 0x41."""
    script_hex = vin.get("scriptSig", {}).get("hex", "")
    pushes = _parse_pushes(script_hex)
    if pushes is None or len(pushes) != 2:
        return False
    sig, pubkey = pushes
    if len(sig) < 1:
        return False
    # pubkey must look like a compressed/uncompressed EC key
    if len(pubkey) not in (33, 65):
        return False
    sighash = sig[-1]
    return sighash == _SIGHASH_ALL


async def analyze_protection(
    tx: dict,
    fetch_tx: TxFetcher,
    _depth: int = 0,
    _max_depth: int = 25,
) -> Protection:
    """Walk the input ancestry. PROTECTED only if every input is a
    standard P2PKH+SIGHASH_ALL spend AND every input's funding tx is
    either confirmed or itself PROTECTED."""
    if _depth > _max_depth:
        return Protection.UNKNOWN

    vins = tx.get("vin", [])
    if not vins:
        return Protection.UNKNOWN

    for vin in vins:
        if "coinbase" in vin:
            return Protection.UNKNOWN
        if not _input_is_standard(vin):
            return Protection.UNPROTECTED

        prev_txid = vin.get("txid")
        if not prev_txid:
            return Protection.UNKNOWN
        try:
            prev = await fetch_tx(prev_txid)
        except Exception:
            return Protection.UNKNOWN

        # If the funding tx is confirmed, this input's chain is anchored.
        if prev.get("confirmations", 0) >= 1:
            continue

        # Unconfirmed parent: recurse. It must itself be PROTECTED.
        parent = await analyze_protection(prev, fetch_tx, _depth + 1, _max_depth)
        if parent is not Protection.PROTECTED:
            return parent if parent is Protection.UNPROTECTED else Protection.UNKNOWN

    return Protection.PROTECTED
