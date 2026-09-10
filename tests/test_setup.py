import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from lovecash.server.setup import create_setup_app  # noqa: E402

XPUB = "xpub6DF5GApwf8FAAoTTwY6Gk2ZXC1uM6kCqqZBBTEC2Bc6ELxQn6ftHxexXxr8RsQpka7racgE7QbVs4JBdCXn7XL63LEF8tAC6u6KrT5eeseS"


@pytest.fixture
def client(tmp_path):
    app = create_setup_app(str(tmp_path / "config.yaml"))
    return TestClient(app, base_url="http://127.0.0.1:8080")


def test_setup_page_served(client):
    resp = client.get("/setup")
    assert resp.status_code == 200
    assert "lovecash setup" in resp.text


def test_check_xpub_valid_shows_derivation_preview(client):
    resp = client.post("/api/setup/check-xpub", json={"xpub": XPUB})
    assert resp.status_code == 200
    addrs = resp.json()["addresses"]
    assert len(addrs) == 3
    assert all(a.startswith("bitcoincash:") for a in addrs)
    assert len(set(addrs)) == 3  # each derived address unique


def test_check_xpub_rejects_private_key(client):
    xprv = "xprv" + XPUB[4:]
    resp = client.post("/api/setup/check-xpub", json={"xpub": xprv})
    assert resp.status_code == 400
    assert "PRIVATE" in resp.json()["detail"].upper()


def test_check_xpub_rejects_garbage(client):
    resp = client.post("/api/setup/check-xpub", json={"xpub": "lol"})
    assert resp.status_code == 400


def test_write_config_manual_action(client, tmp_path):
    resp = client.post(
        "/api/setup/config",
        json={
            "xpub": XPUB,
            "max_strength": 12,
            "max_duration_s": 30,
            "relay_enabled": True,
            "manual_action": "Vibrate",
            "toys": [],
        },
    )
    assert resp.status_code == 200
    written = tmp_path / "config.yaml"
    assert written.exists()
    text = written.read_text()
    assert XPUB in text and "Vibrate" in text
    assert oct(written.stat().st_mode)[-3:] == "600"

    # Written config must load as real Settings
    from lovecash.config import Settings

    settings = Settings.from_yaml(written)
    assert settings.limits.max_strength == 12


def test_write_config_refuses_overwrite(client, tmp_path):
    (tmp_path / "config.yaml").write_text("existing")
    resp = client.post(
        "/api/setup/config",
        json={
            "xpub": XPUB,
            "max_strength": 12,
            "max_duration_s": 30,
            "relay_enabled": True,
            "toys": [],
        },
    )
    assert resp.status_code == 409
    assert (tmp_path / "config.yaml").read_text() == "existing"


def test_write_config_bad_xpub(client):
    resp = client.post(
        "/api/setup/config",
        json={
            "xpub": "xpubgarbage",
            "max_strength": 12,
            "max_duration_s": 30,
            "toys": [],
        },
    )
    assert resp.status_code == 400


def test_setup_write_blocked_cross_site(client, tmp_path):
    resp = client.post(
        "/api/setup/config",
        json={
            "xpub": XPUB,
            "max_strength": 12,
            "max_duration_s": 30,
            "toys": [],
        },
        headers={"sec-fetch-site": "cross-site"},
    )
    assert resp.status_code == 403
    assert not (tmp_path / "config.yaml").exists()


def test_multi_toy_config_scopes_rules(client, tmp_path):
    resp = client.post(
        "/api/setup/config",
        json={
            "xpub": XPUB,
            "max_strength": 15,
            "max_duration_s": 20,
            "relay_enabled": True,
            "toys": [
                {"toy_id": "aa", "name": "solace"},  # known -> Thrusting
                {"toy_id": "bb", "name": "weirdtoy", "action": "Rotate"},
            ],
        },
    )
    assert resp.status_code == 200
    from lovecash.config import Settings

    settings = Settings.from_yaml(tmp_path / "config.yaml")
    assert len(settings.lovense.toys) == 2
    lush_rules = [r for r in settings.rules if r.toy == "aa"]
    other_rules = [r for r in settings.rules if r.toy == "bb"]
    assert lush_rules and other_rules
    assert all(r.action.value == "Thrusting" for r in lush_rules)
    assert all(r.action.value == "Rotate" for r in other_rules)
    assert all(r.strength <= 15 and r.duration_s <= 20 for r in settings.rules)
