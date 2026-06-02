from decimal import Decimal

from lovecash.bch.payment import build_uri, qr_png

ADDR = "bitcoincash:qpm2qsznhks23z7629mms6s4cwef74vcwvy22gdx6a"


def test_uri_with_amount():
    uri = build_uri(ADDR, amount_bch=Decimal("0.001"), label="tip")
    assert uri.startswith("bitcoincash:qpm2")
    assert "amount=0.001" in uri
    assert "label=tip" in uri


def test_qr_png_is_png():
    png = qr_png(build_uri(ADDR))
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
