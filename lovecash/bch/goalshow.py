"""GoalShow covenant claim-tx builder (phase 3 auto-claim).

claim() takes no arguments and needs no signatures — anyone can settle a
met goal. The relay builds and broadcasts it the moment the pot reaches
the goal, so the performer is paid automatically without touching a
wallet. The redeem script is verified against the configured pot address
before broadcast: a constructor/config mismatch produces a tx that could
never validate, so we refuse to send it.
"""

from __future__ import annotations

import hashlib

from lovecash.bch.cashaddr import to_script

# Compiled goal_show.cash artifact bytecode (cashc 0.13.2), hex.
# Constructor args are NOT included — they are prepended as data pushes
# by redeem_script(). Regenerate from contracts/goal_show.json with:
#   node --input-type=module -e "import {asmToScript,scriptToBytecode} from '@cashscript/utils'; \
#     import {binToHex} from '@bitauth/libauth'; import a from './goal_show.json' with {type:'json'}; \
#     console.log(binToHex(scriptToBytecode(asmToScript(a.bytecode))))"
ARTIFACT_HEX = (
    "5479009c63557a82011488c5b175c0009dc3529dc5547a9f6900ce76827701219d760120"
    "7f7752887601207f7555798800cc00c69476028813a26900cd00c78800d17b8800d200cf"
    "8851cd0376a91453797e0288ac7e8851d1557a8851d27b7b58807e88c453a169c4539c63"
    "52d10088686d7551675479519c63c0009dc3519d00ce76827701219d7601207f77528801"
    "207f75547a8800c67ba269c4519d00cd0376a9147b7e0288ac7e8800cc00c602e80394a2"
    "6900d10087777767547a529dc0009dc3529d7bb17500c67b9f6900ce76827701219d7601"
    "207f7752887601207f7553798851ce537a8851cf768277011c9d01147f76577f77018084"
    "0100888176022202a2697600c6a16900cc00c6527994a26900cd00c78800d1537a8800d2"
    "00cf8851cd0376a914537a7e0288ac7e8851cc022202a26951cc7c02e80394a26951d100"
    "88c453a169c4539c6352d100886875516868"
)

CLAIM_FEE_SATS = 1000  # covenant caps the claim fee at 1000 sats
_CLAIM_SELECTOR = b"\x51"  # OP_1: claim is function index 1


def _push(data: bytes) -> bytes:
    n = len(data)
    if n < 0x4C:
        return bytes([n]) + data
    if n <= 0xFF:
        return b"\x4c" + bytes([n]) + data
    return b"\x4d" + n.to_bytes(2, "little") + data


def _scriptnum(n: int) -> bytes:
    """Minimal little-endian sign-magnitude int encoding (positive only)."""
    if n <= 0:
        raise ValueError("scriptnum: positive ints only")
    out = bytearray()
    while n:
        out.append(n & 0xFF)
        n >>= 8
    if out[-1] & 0x80:
        out.append(0)
    return bytes(out)


def _compactsize(n: int) -> bytes:
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + n.to_bytes(2, "little")
    raise ValueError("compactsize too large")


def redeem_script(
    performer_pkh: bytes, goal_sats: int, deadline: int, category_raw: bytes
) -> bytes:
    """Full covenant redeem script: constructor args (reversed declaration
    order, as cashscript lays them out) pushed before the artifact bytecode.
    category_raw is the RAW byte order (reversed display hex)."""
    if len(performer_pkh) != 20 or len(category_raw) != 32:
        raise ValueError("bad constructor arg lengths")
    return (
        _push(category_raw)
        + _push(_scriptnum(deadline))
        + _push(_scriptnum(goal_sats))
        + _push(performer_pkh)
        + bytes.fromhex(ARTIFACT_HEX)
    )


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
    """Serialize the claim transaction. Raises if the constructed redeem
    script does not hash to the configured pot address — a mismatched
    config can never produce a valid claim, so refuse early."""
    redeem = redeem_script(performer_pkh, goal_sats, deadline, category_raw)
    # P2SH32: OP_HASH256 — DOUBLE sha256, matching the 2023 upgrade.
    locking = b"\xaa\x20" + hashlib.sha256(hashlib.sha256(redeem).digest()).digest() + b"\x87"
    if locking != to_script(pot_address):
        raise ValueError("constructed covenant does not match the configured pot address")
    if pot_sats < goal_sats:
        raise ValueError("goal not met")

    script_sig = _CLAIM_SELECTOR + _push(redeem)
    tx = bytearray()
    tx += (2).to_bytes(4, "little")  # version
    tx += b"\x01"  # one input
    tx += bytes.fromhex(pot_txid)[::-1]
    tx += pot_vout.to_bytes(4, "little")
    tx += _compactsize(len(script_sig)) + script_sig
    tx += b"\xfe\xff\xff\xff"  # sequence (cashscript default)
    tx += b"\x01"  # one output
    tx += (pot_sats - CLAIM_FEE_SATS).to_bytes(8, "little")
    out_script = b"\x76\xa9\x14" + performer_pkh + b"\x88\xac"  # P2PKH
    tx += _compactsize(len(out_script)) + out_script
    tx += (0).to_bytes(4, "little")  # locktime
    return tx.hex()
