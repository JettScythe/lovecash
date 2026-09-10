import pytest

from lovecash.config import (
    AlertConfig,
    BchConfig,
    Limits,
    LovenseConfig,
    ServerConfig,
    Settings,
)
from lovecash.server.relay import RelayHub
from lovecash.triggers.events import PaymentTrigger

pytest.importorskip("fastapi")

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


def _control_client(monkeypatch, server_cfg: ServerConfig):
    """TestClient with the network-running orchestrator stubbed out."""
    import asyncio

    from fastapi.testclient import TestClient

    from lovecash.core.orchestrator import Orchestrator
    from lovecash.server.app import create_app

    async def _noop_run(self):
        await asyncio.Event().wait()

    monkeypatch.setattr(Orchestrator, "run", _noop_run)
    cfg = Settings(
        limits=Limits(),
        lovense=LovenseConfig(),
        bch=BchConfig(xpub=XPUB),
        server=server_cfg,
    )
    return TestClient(create_app(cfg), base_url="http://127.0.0.1:8080")


def test_control_routes_allow_local_script(monkeypatch):
    with _control_client(monkeypatch, ServerConfig()) as client:
        assert client.post("/panic").status_code == 200
        assert client.post("/resume").status_code == 200


def test_control_routes_refuse_cross_site_browser_posts(monkeypatch):
    with _control_client(monkeypatch, ServerConfig()) as client:
        resp = client.post("/resume", headers={"Sec-Fetch-Site": "cross-site"})
        assert resp.status_code == 403


def test_control_routes_refuse_dns_rebinding_host(monkeypatch):
    with _control_client(monkeypatch, ServerConfig()) as client:
        resp = client.post("/resume", headers={"Host": "attacker.example.com"})
        assert resp.status_code == 403


def test_control_routes_token_still_enforced_and_sufficient(monkeypatch):
    cfg = ServerConfig(bind_host="127.0.0.1", relay_token="s3cret")  # noqa: S106
    with _control_client(monkeypatch, cfg) as client:
        assert client.post("/panic").status_code == 401
        # A valid token is enough even from a cross-site-looking request:
        # the shared secret is the stronger proof.
        resp = client.post(
            "/panic",
            headers={"X-Relay-Token": "s3cret", "Sec-Fetch-Site": "cross-site"},
        )
        assert resp.status_code == 200


def test_api_status_shape(monkeypatch):
    import asyncio

    from fastapi.testclient import TestClient

    from lovecash.core.orchestrator import Orchestrator
    from lovecash.server.app import create_app

    async def _noop_run(self):
        await asyncio.Event().wait()

    monkeypatch.setattr(Orchestrator, "run", _noop_run)
    cfg = Settings(
        limits=Limits(),
        lovense=LovenseConfig(),
        bch=BchConfig(xpub=XPUB),
        server=ServerConfig(),
    )
    with TestClient(create_app(cfg), base_url="http://127.0.0.1:8080") as client:
        resp = client.get("/api/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True and body["stopped"] is False
        assert body["address"].startswith("bitcoincash:")
        assert body["stats"]["total_sats"] == 0
        assert body["stats"]["recent"] == []
        assert body["alerts"]["sound"] is True


def test_tip_alert_payload_and_min_sats_filter(monkeypatch):
    """Credited tips broadcast an alert (with usd/memo) unless below
    alerts.min_sats; every tip still updates the stats broadcast."""
    import asyncio
    import json

    from fastapi.testclient import TestClient

    from lovecash.core.orchestrator import Orchestrator
    from lovecash.server.app import create_app

    async def _noop_run(self):
        await asyncio.Event().wait()

    monkeypatch.setattr(Orchestrator, "run", _noop_run)
    cfg = Settings(
        limits=Limits(),
        lovense=LovenseConfig(),
        bch=BchConfig(xpub=XPUB),
        server=ServerConfig(alerts=AlertConfig(min_sats=10_000, goal_sats=100_000)),
    )
    app = create_app(cfg)

    with TestClient(app, base_url="http://127.0.0.1:8080") as client:
        status = client.get("/api/status")
        assert status.status_code == 200
        body = status.json()
        assert body["ok"] is True and body["stopped"] is False
        assert body["address"].startswith("bitcoincash:")
        assert body["stats"]["total_sats"] == 0
        assert body["alerts"]["sound"] is True

        orch = app.state.orchestrator

        def drive(txid, sats, memo=None):
            client.portal.call(
                orch._handle_event,
                PaymentTrigger(
                    source_id="t",
                    txid=txid,
                    amount_sats=sats,
                    confirmations=1,
                    memo=memo,
                ),
            )

        with client.websocket_connect("/overlay-ws") as ws:
            drive("big", 50_000, memo="hi")
            msgs = [json.loads(ws.receive_text()), json.loads(ws.receive_text())]
            tip = next(m for m in msgs if m["type"] == "tip")
            assert tip["data"]["amount_sats"] == 50_000
            assert tip["data"]["memo"] == "hi"
            stats_msg = next(m for m in msgs if m["type"] == "stats")
            assert stats_msg["data"]["total_sats"] == 50_000
            assert stats_msg["data"]["goal_sats"] == 100_000

            drive("dust", 500)  # below min_sats: stats only, no alert
            only = json.loads(ws.receive_text())
            assert only["type"] == "stats"
            assert only["data"]["total_sats"] == 50_500
