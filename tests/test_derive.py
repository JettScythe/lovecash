import pytest

from lovecash.bch.derive import XpubDeriver, XpubError

XPUB = "xpub6DF5GApwf8FAAoTTwY6Gk2ZXC1uM6kCqqZBBTEC2Bc6ELxQn6ftHxexXxr8RsQpka7racgE7QbVs4JBdCXn7XL63LEF8tAC6u6KrT5eeseS"
# Independent ground truth: addresses exported from the wallet itself,
# m/44'/145'/0' account -> external branch /0/index.
EXPECTED = {
    0: "bitcoincash:qqhx545cwyqvgtre0t2yn8lwzjzajvfaqg87ruq9gw",
    1: "bitcoincash:qrevp93hwcz8qawjjmdtsgymx37wk2ydhvd5xtd860",
    2: "bitcoincash:qqnd3vggvn9dppkn3tr66daj24fqafvhsqweua4fgv",
    3: "bitcoincash:qppq0jdnq3fpa75ancspdhx9f22g50cxxsxsa8fcn0",
    4: "bitcoincash:qpyyhzpnfd00ep58yg9hlgtus95g66zxpsmpy0ftp6",
    5: "bitcoincash:qq0h8uxt3kprlxmr4tjkt8u3739cp6566u34ekrsy5",
    6: "bitcoincash:qrglfdyphmnuxsu06shqxctuhaps06qmvvtmt0gpj9",
    7: "bitcoincash:qzrs2tn6wgzfrwctj2l4quqeust5wcqmgv8dtgmr5t",
}


def test_derivation_matches_wallet():
    d = XpubDeriver(XPUB)
    for i, addr in EXPECTED.items():
        assert d.address(i) == addr, f"index {i} mismatch"


def test_scripthash_is_hex64():
    d = XpubDeriver(XPUB)
    sh = d.scripthash(0)
    assert len(sh) == 64
    int(sh, 16)


def test_rejects_private_key():
    with pytest.raises(XpubError, match="PRIVATE"):
        XpubDeriver(
            "xprv9s21ZrQH143K3GJpoapnV8SFfukcVBSfeCficPSGfubmSFDxo1c"
            "ud1JBHvpb2dwfBFy7sqxqgbf8AffYf"
        )


def test_rejects_garbage():
    with pytest.raises(XpubError):
        XpubDeriver("not-a-key")
