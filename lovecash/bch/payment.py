import io
from decimal import Decimal
from urllib.parse import quote

import segno

from lovecash.bch.cashaddr import decode  # validates the address


def normalize_address(address: str) -> str:
    """Return a full 'bitcoincash:…' URI-safe address, validating it."""
    decode(address)  # raises ValueError on a bad address — fail loud, fail early
    if ":" in address:
        return address.lower()
    return f"bitcoincash:{address.lower()}"


def build_uri(
    address: str,
    amount_bch: Decimal | float | None = None,
    label: str | None = None,
    message: str | None = None,
) -> str:
    """Build a BIP21 payment URI for Bitcoin Cash wallets."""
    uri = normalize_address(address)
    params: list[str] = []
    if amount_bch is not None:
        # BCH amount, never sats, per BIP21. Trim trailing zeros.
        amt = Decimal(str(amount_bch)).normalize()
        params.append(f"amount={amt:f}")
    if label:
        params.append(f"label={quote(label)}")
    if message:
        params.append(f"message={quote(message)}")
    return uri + ("?" + "&".join(params) if params else "")


def qr_png(uri: str, scale: int = 8) -> bytes:
    """Render a payment URI to PNG bytes (no external image libs)."""
    buf = io.BytesIO()
    segno.make(uri, error="m").save(buf, kind="png", scale=scale, border=2)
    return buf.getvalue()


def qr_svg(uri: str, scale: int = 8) -> bytes:
    buf = io.BytesIO()
    segno.make(uri, error="m").save(buf, kind="svg", scale=scale, border=2)
    return buf.getvalue()
