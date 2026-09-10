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
    await hub.broadcast({"type": "tip", "data": {"amount_sats": 5000}})
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


def _app_client(monkeypatch, server_cfg: ServerConfig):
    """TestClient over a fully-built app with the network stubbed out."""
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


def test_pages_serve(monkeypatch):
    with _app_client(monkeypatch, ServerConfig()) as client:
        for path in ("/overlay", "/dashboard", "/tip"):
            resp = client.get(path)
            assert resp.status_code == 200, path
            assert "<!DOCTYPE html>" in resp.text
        assert "ALERTS" in client.get("/overlay").text
        assert "PANIC STOP" in client.get("/dashboard").text
        assert "Tip with Bitcoin Cash" in client.get("/tip").text
        tip = client.get("/tip").text
        assert 'id="track"' in tip  # live lifecycle stepper
        assert 'class="proof card"' in tip  # trust explainer
        assert 'msg.type === "tip_status"' in tip


def test_overlay_injects_alert_config(monkeypatch):
    cfg = ServerConfig(
        alerts=AlertConfig(goal_sats=250_000, sound=False, accent="#00ffcc")
    )
    with _app_client(monkeypatch, cfg) as client:
        html = client.get("/overlay").text
        assert '"goal_sats": 250000' in html
        assert '"sound": false' in html
        assert "--accent: #00ffcc" in html


def test_qr_endpoints_accept_message(monkeypatch):
    with _app_client(monkeypatch, ServerConfig()) as client:
        resp = client.get("/qr.png", params={"amount": 0.001, "message": "hi"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        uri = client.get("/uri", params={"amount": 0.001, "message": "hi there"})
        assert uri.status_code == 200
        body = uri.json()["uri"]
        assert "amount=0.001" in body
        assert "message=hi%20there" in body
        assert body.startswith("bitcoincash:")


def test_control_routes_allow_local_script(monkeypatch):
    with _app_client(monkeypatch, ServerConfig()) as client:
        assert client.post("/panic").status_code == 200
        assert client.post("/resume").status_code == 200


def test_control_routes_refuse_cross_site_browser_posts(monkeypatch):
    with _app_client(monkeypatch, ServerConfig()) as client:
        resp = client.post("/resume", headers={"Sec-Fetch-Site": "cross-site"})
        assert resp.status_code == 403


def test_control_routes_refuse_dns_rebinding_host(monkeypatch):
    with _app_client(monkeypatch, ServerConfig()) as client:
        resp = client.post("/resume", headers={"Host": "attacker.example.com"})
        assert resp.status_code == 403


def test_control_routes_token_still_enforced_and_sufficient(monkeypatch):
    cfg = ServerConfig(bind_host="127.0.0.1", relay_token="s3cret")  # noqa: S106
    with _app_client(monkeypatch, cfg) as client:
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


def _settings_client(monkeypatch, tmp_path):
    """App wired to a real config path so settings saves persist."""
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
    path = tmp_path / "config.yaml"
    path.write_text(f"bch:\n  xpub: {XPUB}\n")
    return TestClient(
        create_app(cfg, str(path)), base_url="http://127.0.0.1:8080"
    ), path


def test_settings_roundtrip_hot_applies_and_persists(monkeypatch, tmp_path):
    client, path = _settings_client(monkeypatch, tmp_path)
    with client:
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        before = resp.json()
        assert before["limits"]["max_strength"] == 12
        assert before["persisted"] is True

        body = {
            "limits": {**before["limits"], "max_strength": 7},
            "rules": [
                {
                    "name": "buzz",
                    "min_sats": 1000,
                    "action": "Vibrate",
                    "strength": 5,
                    "duration_s": 3,
                }
            ],
            "alerts": {**before["alerts"], "goal_sats": 42_000},
        }
        resp = client.post("/api/settings", json=body)
        assert resp.status_code == 200
        assert resp.json() == {
            "ok": True,
            "applied": ["limits", "rules", "alerts"],
            "persisted": True,
        }

        # hot-applied in memory
        orch = client.app.state.orchestrator
        assert orch._settings.limits.max_strength == 7
        assert (
            orch._engine.resolve_all(
                PaymentTrigger(
                    source_id="t", txid="x", amount_sats=5000, confirmations=1
                )
            )[0][0].strength
            == 5
        )

        # persisted to disk, loadable, untouched sections intact
        from lovecash.config import Settings as S

        reloaded = S.from_yaml(path)
        assert reloaded.limits.max_strength == 7
        assert reloaded.server.alerts.goal_sats == 42_000
        assert reloaded.rules[0].name == "buzz"
        assert reloaded.bch.xpub == XPUB
        assert oct(path.stat().st_mode)[-3:] == "600"


def test_settings_post_rejects_invalid_rules(monkeypatch, tmp_path):
    client, path = _settings_client(monkeypatch, tmp_path)
    with client:
        resp = client.post(
            "/api/settings",
            json={"rules": [{"name": "x"}]},  # missing required fields
        )
        assert resp.status_code == 422


def test_settings_requires_local_or_token(monkeypatch, tmp_path):
    client, path = _settings_client(monkeypatch, tmp_path)
    with client:
        resp = client.post(
            "/api/settings",
            json={"alerts": {"sound": False}},
            headers={"Sec-Fetch-Site": "cross-site"},
        )
        assert resp.status_code == 403


def test_settings_save_broadcasts_to_overlays(monkeypatch, tmp_path):
    """Goal/accent changes must reach open overlays immediately, not
    after the next tip (overlay goal bar is stats-message driven)."""
    import json as _json

    client, path = _settings_client(monkeypatch, tmp_path)
    with client, client.websocket_connect("/overlay-ws") as ws:
        before = client.get("/api/settings").json()
        body = {"alerts": {**before["alerts"], "goal_sats": 99_000}}
        assert client.post("/api/settings", json=body).status_code == 200
        msgs = [_json.loads(ws.receive_text()), _json.loads(ws.receive_text())]
        stats = next(m for m in msgs if m["type"] == "stats")
        alerts = next(m for m in msgs if m["type"] == "alerts")
        assert stats["data"]["goal_sats"] == 99_000
        assert alerts["data"]["goal_sats"] == 99_000


def test_goal_visibility_toggle_persists_and_broadcasts(monkeypatch, tmp_path):
    import json as _json

    client, path = _settings_client(monkeypatch, tmp_path)
    with client, client.websocket_connect("/overlay-ws") as ws:
        before = client.get("/api/settings").json()
        assert before["alerts"]["show_goal"] is True  # default on
        body = {"alerts": {**before["alerts"], "goal_sats": 50_000, "show_goal": False}}
        assert client.post("/api/settings", json=body).status_code == 200
        msgs = [_json.loads(ws.receive_text()), _json.loads(ws.receive_text())]
        alerts = next(m for m in msgs if m["type"] == "alerts")
        assert alerts["data"]["show_goal"] is False
        assert alerts["data"]["goal_sats"] == 50_000

        from lovecash.config import Settings as S

        reloaded = S.from_yaml(path)
        assert reloaded.server.alerts.show_goal is False
        assert reloaded.server.alerts.goal_sats == 50_000
