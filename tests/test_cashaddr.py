from lovecash.bch.cashaddr import decode, to_scripthash

ADDR = "bitcoincash:qqhx545cwyqvgtre0t2yn8lwzjzajvfaqg87ruq9gw"


def test_decode_kind_p2pkh():
    kind, h160 = decode(ADDR)
    assert kind == 0
    assert len(h160) == 20


def test_scripthash_is_hex64():
    sh = to_scripthash(ADDR)
    assert len(sh) == 64
    int(sh, 16)  # parses as hex


def test_token_variant_round_trip():
    from lovecash.bch.cashaddr import token_variant

    z_addr = token_variant(ADDR)
    kind_q, h_q = decode(ADDR)
    kind_z, h_z = decode(z_addr)
    assert kind_q == 0
    assert kind_z == 2
    assert h_q == h_z
    assert token_variant(z_addr) == z_addr  # idempotent


def test_token_aware_kind_shares_scripthash():
    from lovecash.bch.cashaddr import token_variant

    assert to_scripthash(token_variant(ADDR)) == to_scripthash(ADDR)


def test_token_aware_encode_matches_decode():
    from lovecash.bch.cashaddr import encode_p2pkh

    pubkey = "02" + "ab" * 32
    addr = encode_p2pkh(pubkey, token_aware=True)
    kind, _ = decode(addr)
    assert kind == 2
