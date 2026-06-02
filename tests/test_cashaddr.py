from lovecash.bch.cashaddr import decode, to_scripthash

# Well-known CashAddr test vector (P2PKH).

ADDR = "bitcoincash:qpm2qsznhks23z7629mms6s4cwef74vcwvy22gdx6a"


def test_decode_kind_p2pkh():
    kind, h160 = decode(ADDR)
    assert kind == 0
    assert len(h160) == 20


def test_scripthash_is_hex64():
    sh = to_scripthash(ADDR)
    assert len(sh) == 64
    int(sh, 16)  # parses as hex
