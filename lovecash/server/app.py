import asyncio
import logging
from contextlib import asynccontextmanager
from decimal import Decimal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket
from fastapi.responses import HTMLResponse, Response
from fastapi.websockets import WebSocketDisconnect

from lovecash.bch.payment import build_uri, qr_png, qr_svg
from lovecash.config import Settings
from lovecash.core.orchestrator import Orchestrator
from lovecash.server.relay import RelayHub
from lovecash.server.templates import OVERLAY_HTML

log = logging.getLogger("lovecash.server")

_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def create_app(settings: Settings) -> FastAPI:
    # Guardrail: refuse to expose control routes publicly without a token.
    if settings.server.bind_host not in _LOOPBACK and not settings.server.relay_token:
        raise RuntimeError(
            "Relay is binding to a public address without a relay_token. "
            "Set server.relay_token (a long random secret) or bind to "
            "127.0.0.1. Refusing to start to avoid an unauthenticated "
            "/resume endpoint that could clear a panic stop."
        )

    hub = RelayHub()
    orchestrator = Orchestrator(settings)
    orchestrator.add_observer(hub.broadcast_event)

    async def _on_status(state) -> None:
        await hub.broadcast({"type": "status", "data": {"connection": state}})

    async def _on_tip_status(tip_id: str, status: str, extra: dict) -> None:
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

    def auth(request: Request, x_relay_token: str | None = Header(default=None)) -> None:
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
            raise HTTPException(status_code=403, detail="cross-site control request refused")
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

    # --- OBS-facing endpoints (no auth: read-only, no funds touched) ---

    @app.get("/overlay", response_class=HTMLResponse)
    async def overlay_page() -> str:
        """Add THIS url as a Browser Source in OBS. That's the whole setup."""
        return OVERLAY_HTML

    @app.get("/qr.png")
    async def qr_png_ep(
        amount: float | None = Query(default=None, ge=0),
        scale: int = Query(default=8, ge=1, le=20),
    ) -> Response:
        uri = build_uri(
            orchestrator.current_address(),
            amount_bch=Decimal(str(amount)) if amount else None,
            label="lovecash tip",
        )
        return Response(content=qr_png(uri, scale), media_type="image/png")

    @app.get("/qr.svg")
    async def qr_svg_ep(amount: float | None = Query(default=None, ge=0)):
        uri = build_uri(
            orchestrator.current_address(),
            amount_bch=Decimal(str(amount)) if amount else None,
            label="lovecash tip",
        )
        return Response(content=qr_svg(uri), media_type="image/svg+xml")

    @app.get("/uri")
    async def uri_ep(amount: float | None = Query(default=None, ge=0)) -> dict:
        return {
            "uri": build_uri(
                orchestrator.current_address(),
                amount_bch=Decimal(str(amount)) if amount else None,
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

    @app.websocket("/overlay-ws")
    async def overlay_ws(ws: WebSocket) -> None:
        await ws.accept()
        q = hub.register()
        try:
            while True:
                await ws.send_text(await q.get())
        except WebSocketDisconnect:
            pass
        finally:
            hub.unregister(q)

    return app
