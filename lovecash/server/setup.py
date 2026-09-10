"""Setup mode: a loopback-only FastAPI app serving the web onboarding
wizard when no valid config exists yet. No orchestrator, no relay —
just config authoring."""

import logging

from anyio import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, ValidationError

from lovecash.bch.derive import XpubDeriver, XpubError
from lovecash.lovense.toys import ToyCategory
from lovecash.models import Action
from lovecash.onboard import build_rules, detect_toys, render_config, toy_defaults
from lovecash.server.ui.setup import SETUP_HTML

log = logging.getLogger("lovecash.setup")

_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class XpubCheck(BaseModel):
    xpub: str


class ToySpecIn(BaseModel):
    toy_id: str
    name: str
    action: str | None = None  # user-picked, for toys not in KNOWN_TOYS


class ConfigIn(BaseModel):
    xpub: str
    max_strength: int = Field(ge=1, le=20)
    max_duration_s: float = Field(ge=1, le=3600)
    relay_enabled: bool = True
    manual_action: str | None = None  # used when no toys detected
    toys: list[ToySpecIn] = []


def _loopback_only(request: Request) -> None:
    """Setup writes config.yaml to disk — never from off-machine."""
    from urllib.parse import urlsplit

    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(status_code=403, detail="cross-site setup refused")
    host = urlsplit(f"//{request.headers.get('host', '')}").hostname or ""
    if host.lower() not in _LOOPBACK:
        raise HTTPException(status_code=403, detail="setup is local-only")


def _parse_action(raw: str | None) -> Action:
    try:
        return Action((raw or "Vibrate").strip().capitalize())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"unknown action: {raw}") from None


def create_setup_app(config_path: str = "config.yaml") -> FastAPI:
    app = FastAPI(title="lovecash setup")

    @app.get("/setup", response_class=HTMLResponse)
    async def setup_page() -> str:
        return SETUP_HTML

    @app.get("/api/setup/toys")
    async def setup_toys(request: Request) -> dict:
        _loopback_only(request)
        detected = await detect_toys()
        toys = []
        for toy_id, name in detected:
            defaults = toy_defaults(name)
            toys.append(
                {
                    "id": toy_id,
                    "name": name,
                    "known": defaults is not None,
                    "action": (defaults[0].value if defaults else "Vibrate"),
                }
            )
        return {"toys": toys}

    @app.post("/api/setup/check-xpub")
    async def check_xpub(body: XpubCheck) -> dict:
        try:
            deriver = XpubDeriver(body.xpub)
        except XpubError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"addresses": [deriver.address(i) for i in range(3)]}

    @app.post("/api/setup/config")
    async def write_config(body: ConfigIn, request: Request) -> dict:
        _loopback_only(request)
        path = Path(config_path)
        if await path.exists():
            raise HTTPException(
                status_code=409,
                detail=f"{config_path} already exists — refusing to overwrite. "
                "Delete it or use `lovecash init`.",
            )

        multi = len(body.toys) > 1
        rules: list[dict] = []
        toy_specs: list[dict] = []
        if not body.toys:
            rules = build_rules(
                _parse_action(body.manual_action),
                ToyCategory.VIBRATOR,
                None,
                "",
                False,
                body.max_strength,
                body.max_duration_s,
            )
        else:
            for toy in body.toys:
                defaults = toy_defaults(toy.name)
                if defaults is not None:
                    action, category = defaults
                else:
                    action, category = _parse_action(toy.action), ToyCategory.VIBRATOR
                rules.extend(
                    build_rules(
                        action,
                        category,
                        toy.toy_id,
                        toy.name,
                        multi,
                        body.max_strength,
                        body.max_duration_s,
                    )
                )
                if multi:
                    toy_specs.append({"toy_id": toy.toy_id})

        try:
            rendered = render_config(
                body.xpub,
                body.max_strength,
                body.max_duration_s,
                body.relay_enabled,
                rules,
                toy_specs,
            )
        except XpubError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValidationError as exc:
            log.exception("generated config failed validation")
            raise HTTPException(
                status_code=500, detail="generated config invalid — template bug"
            ) from exc

        await path.write_text(rendered)
        await path.chmod(0o600)  # xpub reveals address history — owner-only
        resolved = await path.resolve()
        log.info("Setup wrote %s", resolved)
        return {"ok": True, "path": str(resolved)}

    return app
