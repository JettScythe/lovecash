from lovecash.bch.dsproof import Protection, analyze_protection


def _push(data_hex: str) -> str:
    n = len(data_hex) // 2
    return f"{n:02x}{data_hex}"


# 64-byte Schnorr sig + 1 sighash byte, then 33-byte pubkey
_SIG64 = "ab" * 64
_PUB33 = "02" + "cd" * 32


def _p2pkh_hex(sighash: str = "41") -> str:
    sig_with_hash = _SIG64 + sighash
    return _push(sig_with_hash) + _push(_PUB33)


def _p2pkh_input(txid: str, sighash: str = "41") -> dict:
    return {"txid": txid, "scriptSig": {"hex": _p2pkh_hex(sighash)}}


def _p2sh_input(txid: str) -> dict:
    # three pushes + a redeem script -> not two clean pushes
    redeem = "5221" + ("ab" * 33) + "21" + ("cd" * 33) + "52ae"
    h = _push(_SIG64 + "41") + _push(_SIG64 + "41") + _push(redeem)
    return {"txid": txid, "scriptSig": {"hex": h}}


def _tx(vins: list[dict], confirmations: int = 0) -> dict:
    return {"vin": vins, "confirmations": confirmations}


async def _fetch_factory(store: dict):
    async def fetch(txid: str) -> dict:
        return store[txid]

    return fetch


async def test_all_p2pkh_confirmed_ancestors_is_protected():
    store = {"parent": _tx([_p2pkh_input("grand")], confirmations=5)}
    fetch = await _fetch_factory(store)
    tx = _tx([_p2pkh_input("parent")], confirmations=0)
    assert await analyze_protection(tx, fetch) is Protection.PROTECTED


async def test_any_p2sh_input_is_unprotected():
    store = {"parent": _tx([_p2pkh_input("g")], confirmations=5)}
    fetch = await _fetch_factory(store)
    tx = _tx([_p2pkh_input("parent"), _p2sh_input("other")], confirmations=0)
    assert await analyze_protection(tx, fetch) is Protection.UNPROTECTED


async def test_non_sighash_all_is_unprotected():
    store = {"parent": _tx([_p2pkh_input("g")], confirmations=5)}
    fetch = await _fetch_factory(store)
    # 0xc2 = ALL|ANYONECANPAY|FORKID, not plain ALL -> not protected
    tx = _tx([_p2pkh_input("parent", sighash="c2")], confirmations=0)
    assert await analyze_protection(tx, fetch) is Protection.UNPROTECTED


async def test_unconfirmed_p2pkh_chain_is_protected():
    # parent unconfirmed but itself all-p2pkh from a confirmed grandparent
    store = {
        "parent": _tx([_p2pkh_input("grand")], confirmations=0),
        "grand": _tx([_p2pkh_input("ggrand")], confirmations=10),
    }
    fetch = await _fetch_factory(store)
    tx = _tx([_p2pkh_input("parent")], confirmations=0)
    assert await analyze_protection(tx, fetch) is Protection.PROTECTED


async def test_unconfirmed_p2sh_ancestor_breaks_chain():
    store = {
        "parent": _tx([_p2sh_input("grand")], confirmations=0),
    }
    fetch = await _fetch_factory(store)
    tx = _tx([_p2pkh_input("parent")], confirmations=0)
    assert await analyze_protection(tx, fetch) is Protection.UNPROTECTED


async def test_fetch_failure_is_unknown():
    async def fetch(txid: str) -> dict:
        raise ConnectionError("node down")

    tx = _tx([_p2pkh_input("parent")], confirmations=0)
    assert await analyze_protection(tx, fetch) is Protection.UNKNOWN


async def test_coinbase_input_is_unknown():
    async def fetch(txid: str) -> dict:
        raise AssertionError("should not fetch")

    tx = {"vin": [{"coinbase": "03..."}], "confirmations": 0}
    assert await analyze_protection(tx, fetch) is Protection.UNKNOWN


async def test_deep_chain_caps_to_unknown():
    # a chain longer than max_depth must not infinite-loop; returns unknown
    store = {}
    for i in range(30):
        store[f"t{i}"] = _tx([_p2pkh_input(f"t{i + 1}")], confirmations=0)
    store["t30"] = _tx([_p2pkh_input("base")], confirmations=0)
    fetch = await _fetch_factory(store)
    tx = _tx([_p2pkh_input("t0")], confirmations=0)
    result = await analyze_protection(tx, fetch)
    assert result in (Protection.UNKNOWN, Protection.UNPROTECTED)
