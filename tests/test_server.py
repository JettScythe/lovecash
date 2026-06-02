import pytest

from lovecash.config import (
    BchConfig,
    Limits,
    LovenseConfig,
    ServerConfig,
    Settings,
)
from lovecash.models import TipEvent
from lovecash.server.relay import RelayHub

pytest.importorskip("fastapi")
ADDR = "bitcoincash:qpm2qsznhks23z7629mms6s4cwef74vcwvy22gdx6a"


async def test_relay_fans_out_tips():
    hub = RelayHub()
    a = hub.register()
    b = hub.register()
    await hub.broadcast_tip(TipEvent(txid="x", amount_sats=5000, confirmations=1))
    msg_a = await a.get()
    msg_b = await b.get()
    assert "5000" in msg_a and msg_a == msg_b


def test_public_bind_without_token_refuses():
    from lovecash.server.app import create_app

    cfg = Settings(
        limits=Limits(),
        lovense=LovenseConfig(),
        bch=BchConfig(address=ADDR),
        server=ServerConfig(bind_host="0.0.0.0", relay_token=None),
    )
    with pytest.raises(RuntimeError, match="relay_token"):
        create_app(cfg)
