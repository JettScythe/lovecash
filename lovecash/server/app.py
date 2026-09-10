import asyncio
import logging
import time
from collections import deque
from contextlib import asynccontextmanager
from decimal import Decimal
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket
from fastapi.responses import HTMLResponse, Response
from fastapi.websockets import WebSocketDisconnect
from pydantic import BaseModel

from lovecash.bch.payment import build_uri, qr_png, qr_svg
from lovecash.config import AlertConfig, Limits, Settings
from lovecash.core.orchestrator import Orchestrator
from lovecash.models import TipRule, TokenRule
from lovecash.server.relay import RelayHub
from lovecash.server.ui import DASHBOARD_HTML, TIP_HTML, render_overlay
from lovecash.triggers.events import TriggerEvent
from lovecash.triggers.status import TipStatus

log = logging.getLogger("lovecash.server")

_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class SettingsUpdate(BaseModel):
    """Partial live-settings save from the dashboard. Omitted sections
    stay as-is. xpub/servers/toys are restart-level and not offered."""

    limits: Limits | None = None
    rules: list[TipRule] | None = None
    token_rules: list[TokenRule] | None = None
    alerts: AlertConfig | None = None


def _apply_in_place(model: BaseModel, new: BaseModel) -> None:
    # Mutate, don't rebind: players/overlay closures hold this object.
    for name, value in new:
        setattr(model, name, value)


class SessionStats:
    """In-memory tally of credited tips for the overlay and dashboard."""

    def __init__(self, max_recent: int = 50) -> None:
        self.started_at = time.time()
        self.total_sats = 0
        self.count = 0
        self.top_sats = 0
        self.recent: deque[dict] = deque(maxlen=max_recent)
        self._by_id: dict[str, dict] = {}

    def record_tip(self, event: TriggerEvent, usd: float | None) -> None:
        if event.kind != "payment":
            return
        self.total_sats += event.amount_sats
        self.count += 1
        self.top_sats = max(self.top_sats, event.amount_sats)
        entry = {
            "id": event.txid,
            "amount_sats": event.amount_sats,
            "usd": round(event.amount_sats / 1e8 * usd, 2) if usd else None,
            "memo": event.memo,
            "status": TipStatus.ACTIVE,
            "at": time.time(),
        }
        self.recent.appendleft(entry)
        self._by_id[event.txid] = entry

    def record_status(self, tip_id: str, status: TipStatus) -> None:
        entry = self._by_id.get(tip_id)
        if entry is not None:
            entry["status"] = status

    def snapshot(self) -> dict:
        return {
            "started_at": self.started_at,
            "total_sats": self.total_sats,
            "count": self.count,
            "top_sats": self.top_sats,
            "recent": list(self.recent),
        }


def create_app(settings: Settings, config_path: str | None = None) -> FastAPI:
    # Guardrail: refuse to expose control routes publicly without a token.
    if settings.server.bind_host not in _LOOPBACK and not settings.server.relay_token:
        raise RuntimeError(
            "Relay is binding to a public address without a relay_token. "
            "Set server.relay_token (a long random secret) or bind to "
            "127.0.0.1. Refusing to start to avoid an unauthenticated "
            "/resume endpoint that could clear a panic stop."
        )

    hub = RelayHub()
    stats = SessionStats()
    alerts = settings.server.alerts
    orchestrator = Orchestrator(settings)

    async def _on_event(event: TriggerEvent) -> None:
        """Credited tips: record stats, broadcast the alert (config-shaped)
        and the running totals for the goal bar."""
        if event.kind != "payment":
            return
        price = orchestrator.current_price_usd()
        stats.record_tip(event, price)
        if event.amount_sats >= alerts.min_sats:
            usd = round(event.amount_sats / 1e8 * price, 2) if price else None
            await hub.broadcast(
                {
                    "type": "tip",
                    "data": {
                        "amount_sats": event.amount_sats,
                        "txid": event.txid,
                        "confirmations": event.confirmations,
                        "usd": usd,
                        "memo": event.memo,
                    },
                }
            )
        await hub.broadcast(
            {
                "type": "stats",
                "data": {
                    "total_sats": stats.total_sats,
                    "count": stats.count,
                    "goal_sats": alerts.goal_sats,
                },
            }
        )

    orchestrator.add_observer(_on_event)

    async def _on_status(state) -> None:
        await hub.broadcast({"type": "status", "data": {"connection": state}})

    async def _on_tip_status(tip_id: str, status: TipStatus, extra: dict) -> None:
        stats.record_status(tip_id, status)
        await hub.broadcast(
            {"type": "tip_status", "data": {"id": tip_id, "status": status, **extra}}
        )

    async def _on_address(addr: str, index: int) -> None:
        await hub.broadcast(
            {"type": "address", "data": {"address": addr, "index": index}}
        )

    orchestrator.add_status_observer(_on_status)
    orchestrator.add_tip_status_observer(_on_tip_status)
    orchestrator.add_address_observer(_on_address)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        task = asyncio.create_task(orchestrator.run())
        yield
        task.cancel()
        await orchestrator.shutdown()

    app = FastAPI(title="lovecash relay", lifespan=lifespan)
    app.state.orchestrator = orchestrator
    app.state.hub = hub
    app.state.stats = stats

    def auth(
        request: Request, x_relay_token: str | None = Header(default=None)
    ) -> None:
        token = settings.server.relay_token
        if token:
            if x_relay_token != token:
                raise HTTPException(status_code=401, detail="bad relay token")
            return  # token-authenticated callers are trusted as-is
        # No token (loopback-only relay): a drive-by webpage must never
        # clear a panic stop. Browsers tag cross-site requests with
        # Sec-Fetch-Site, and DNS-rebinding attacks arrive with a
        # non-loopback Host — refuse both. Local scripts and curl keep
        # working.
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(
                status_code=403, detail="cross-site control request refused"
            )
        host = urlsplit(f"//{request.headers.get('host', '')}").hostname or ""
        if host.lower() not in _LOOPBACK:
            raise HTTPException(
                status_code=403, detail="control requests must come from this machine"
            )

    @app.get("/health")
    async def health() -> dict:
        return {
            "ok": True,
            "stopped": orchestrator.safety.stopped,
            "connection": orchestrator.connection_state,
        }

    @app.get("/api/status")
    async def api_status() -> dict:
        """Everything the performer dashboard needs in one poll."""
        return {
            "ok": True,
            "stopped": orchestrator.safety.stopped,
            "connection": orchestrator.connection_state,
            "address": orchestrator.current_tip_address(),
            "price_usd": orchestrator.current_price_usd(),
            "stats": stats.snapshot(),
            "alerts": alerts.model_dump(),
        }

    @app.get("/api/toys")
    async def api_toys() -> dict:
        """Proxy the local Lovense Connect /GetToys for the dashboard."""
        cfg = settings.lovense
        scheme = "https" if cfg.use_https else "http"
        try:
            # Lovense Connect's local API uses a self-signed cert.
            async with httpx.AsyncClient(verify=False, timeout=4) as hc:  # noqa: S501
                resp = await hc.get(f"{scheme}://{cfg.host}:{cfg.port}/GetToys")
            data = resp.json().get("data", {}) or {}
            toys = [
                {
                    "id": tid,
                    "name": t.get("name", "Unknown"),
                    "online": t.get("status") == 1,
                    "battery": t.get("battery"),
                }
                for tid, t in data.items()
            ]
            return {"ok": True, "toys": toys}
        except Exception:
            return {"ok": False, "toys": []}

    # --- OBS-facing endpoints (no auth: read-only, no funds touched) ---

    @app.get("/overlay", response_class=HTMLResponse)
    async def overlay_page() -> str:
        """Add THIS url as a Browser Source in OBS. That's the whole setup."""
        return render_overlay(alerts)

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_page() -> str:
        """Performer control panel: status, stats, toys, panic/resume."""
        return DASHBOARD_HTML

    @app.get("/tip", response_class=HTMLResponse)
    async def tip_page() -> str:
        """Public viewer tipping page: amount picker + live QR."""
        return TIP_HTML

    @app.get("/qr.png")
    async def qr_png_ep(
        amount: float | None = Query(default=None, ge=0),
        scale: int = Query(default=8, ge=1, le=20),
        message: str | None = Query(default=None, max_length=200),
    ) -> Response:
        uri = build_uri(
            orchestrator.current_tip_address(),
            amount_bch=Decimal(str(amount)) if amount else None,
            label="lovecash tip",
            message=message,
        )
        return Response(content=qr_png(uri, scale), media_type="image/png")

    @app.get("/qr.svg")
    async def qr_svg_ep(
        amount: float | None = Query(default=None, ge=0),
        message: str | None = Query(default=None, max_length=200),
    ):
        uri = build_uri(
            orchestrator.current_tip_address(),
            amount_bch=Decimal(str(amount)) if amount else None,
            label="lovecash tip",
            message=message,
        )
        return Response(content=qr_svg(uri), media_type="image/svg+xml")

    @app.get("/uri")
    async def uri_ep(
        amount: float | None = Query(default=None, ge=0),
        message: str | None = Query(default=None, max_length=200),
    ) -> dict:
        return {
            "uri": build_uri(
                orchestrator.current_tip_address(),
                amount_bch=Decimal(str(amount)) if amount else None,
                message=message,
            )
        }

    # --- Performer control (auth required) ---

    @app.post("/panic", dependencies=[Depends(auth)])
    async def panic() -> dict:
        orchestrator.safety.panic_stop()
        await orchestrator.router.stop_all()

        return {"stopped": True}

    @app.post("/resume", dependencies=[Depends(auth)])
    async def resume() -> dict:
        orchestrator.safety.resume()
        return {"stopped": False}

    @app.get("/api/settings", dependencies=[Depends(auth)])
    async def get_settings() -> dict:
        """Current live-editable settings for the dashboard form."""
        return {
            "limits": settings.limits.model_dump(),
            "rules": [r.model_dump() for r in settings.rules],
            "token_rules": [r.model_dump() for r in settings.token_rules],
            "alerts": alerts.model_dump(),
            "persisted": config_path is not None,
        }

    @app.post("/api/settings", dependencies=[Depends(auth)])
    async def update_settings(body: SettingsUpdate) -> dict:
        """Hot-apply + persist. Takes effect on the next tip — no restart."""
        applied: list[str] = []
        if body.limits is not None:
            _apply_in_place(settings.limits, body.limits)
            orchestrator.router.refresh_limits()  # per-toy controller copies
            applied.append("limits")
        if body.rules is not None or body.token_rules is not None:
            token_rules = (
                body.token_rules
                if body.token_rules is not None
                else settings.token_rules
            )
            rules = body.rules if body.rules is not None else settings.rules
            orchestrator.set_rules(rules, token_rules)
            settings.rules = rules
            settings.token_rules = token_rules
            applied.append("rules")
        if body.alerts is not None:
            _apply_in_place(alerts, body.alerts)
            applied.append("alerts")
        persisted = False
        if config_path is not None and applied:
            settings.save_yaml(config_path)
            persisted = True
        # Push the change to open overlays/dashboards immediately —
        # otherwise a new goal/accent only shows after the next tip.
        if applied:
            await hub.broadcast(
                {
                    "type": "stats",
                    "data": {
                        "total_sats": stats.total_sats,
                        "count": stats.count,
                        "goal_sats": alerts.goal_sats,
                    },
                }
            )
            await hub.broadcast({"type": "alerts", "data": alerts.model_dump()})
        return {"ok": True, "applied": applied, "persisted": persisted}

    @app.websocket("/overlay-ws")
    async def overlay_ws(ws: WebSocket) -> None:
        await ws.accept()
        q = hub.register()
        try:
            while True:
                await ws.send_text(await q.get())
        except WebSocketDisconnect, RuntimeError:
            pass  # client went away (send on a closed socket: RuntimeError)
        finally:
            hub.unregister(q)

    return app
