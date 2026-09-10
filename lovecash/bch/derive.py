from hdwallet import HDWallet
from hdwallet.symbols import BCH

from lovecash.bch.cashaddr import encode_p2pkh


class XpubError(ValueError):
    pass


class XpubDeriver:
    """Watch-only BCH address derivation from an account-level xpub."""

    def __init__(self, xpub: str, branch: int = 0) -> None:
        x = xpub.strip()
        # "prv" catches xprv/yprv/zprv/tprv; "Ltpv" is the odd one out.
        if x[:4] == "Ltpv" or "prv" in x[:6].lower():
            raise XpubError(
                "That looks like a PRIVATE key (xprv...). Never paste a "
                "private key. lovecash needs your PUBLIC key (xpub...)."
            )
        self._xpub = x
        self._branch = branch
        try:
            self._wallet_at(0)  # probe
        except XpubError:
            raise
        except Exception as exc:
            raise XpubError(f"Invalid extended public key: {exc}") from exc

    def _wallet_at(self, index: int) -> HDWallet:
        hd = HDWallet(symbol=BCH)
        hd.from_xpublic_key(xpublic_key=self._xpub, strict=False)
        hd.from_path(f"m/{self._branch}/{index}")
        return hd

    def address(self, index: int) -> str:
        # hdwallet derives correctly; we encode CashAddr ourselves because
        # hdwallet v2 emits a malformed base58 'bitcoincash:C...' form.
        return encode_p2pkh(self._wallet_at(index).public_key())

    def scripthash(self, index: int) -> str:
        from lovecash.bch.cashaddr import to_scripthash

        return to_scripthash(self.address(index))
