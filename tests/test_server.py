import pytest

from lovecash.config import (
    BchConfig,
    Limits,
    LovenseConfig,
    ServerConfig,
    Settings,
)
from lovecash.server.relay import RelayHub
from lovecash.triggers.events import PaymentTrigger

pytest.importorskip("fastapi")
ADDR = "bitcoincash:qqhx545cwyqvgtre0t2yn8lwzjzajvfaqg87ruq9gw"

XPUB = "xpub6DF5GApwf8FAAoTTwY6Gk2ZXC1uM6kCqqZBBTEC2Bc6ELxQn6ftHxexXxr8RsQpka7racgE7QbVs4JBdCXn7XL63LEF8tAC6u6KrT5eeseS"


async def test_relay_fans_out_tips():
    hub = RelayHub()
    a = hub.register()
    b = hub.register()
    await hub.broadcast_event(
        PaymentTrigger(source_id="t", txid="x", amount_sats=5000, confirmations=1)
    )
    msg_a = await a.get()
    msg_b = await b.get()
    assert "5000" in msg_a and msg_a == msg_b


async def test_relay_status_broadcast():
    hub = RelayHub()
    q = hub.register()
    await hub.broadcast({"type": "status", "data": {"connection": "down"}})
    msg = await q.get()
    assert "down" in msg


def test_public_bind_without_token_refuses():
    from lovecash.server.app import create_app

    cfg = Settings(
        limits=Limits(),
        lovense=LovenseConfig(),
        bch=BchConfig(xpub=XPUB),
        server=ServerConfig(bind_host="0.0.0.0", relay_token=None),
    )
    with pytest.raises(RuntimeError, match="relay_token"):
        create_app(cfg)
