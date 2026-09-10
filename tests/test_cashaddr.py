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


# Cross-implementation vector: produced by cashscript 0.13 (address.mjs)
# for a fixed GoalShow parameter set.
P2SH32 = "bchtest:p0a7vksz5vwdmeqg669u70e7mndfr6ns2ep0vpre4046repxc254jdggwk2pg"
P2SH32_TOKADDR = "bchtest:r0a7vksz5vwdmeqg669u70e7mndfr6ns2ep0vpre4046repxc254jlm500tcr"


def test_p2sh32_decode_32_bytes():
    kind, h = decode(P2SH32)
    assert kind == 1
    assert len(h) == 32


def test_p2sh32_token_aware_same_script():
    from lovecash.bch.cashaddr import to_script

    kind, h = decode(P2SH32_TOKADDR)
    assert kind == 3
    assert len(h) == 32
    assert to_script(P2SH32) == to_script(P2SH32_TOKADDR)
    # P2SH32 uses OP_HASH256 (0xaa) — cross-checked against a real
    # cashscript covenant UTXO on chipnet.
    assert to_script(P2SH32) == b"\xaa\x20" + h + b"\x87"


def test_p2sh32_round_trip_reencode():
    from lovecash.bch.cashaddr import _encode

    kind, h = decode(P2SH32)
    assert _encode(h, version=0x0B, prefix="bchtest") == P2SH32


def test_p2sh32_scripthash_is_hex64():
    from lovecash.bch.cashaddr import to_scripthash

    sh = to_scripthash(P2SH32_TOKADDR)
    assert len(sh) == 64
    int(sh, 16)
