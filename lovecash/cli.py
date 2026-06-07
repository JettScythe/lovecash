import asyncio
import logging

import typer
import yaml
from anyio import Path
from httpx import AsyncClient
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from lovecash.bch.cashaddr import to_scripthash
from lovecash.bch.derive import XpubDeriver, XpubError
from lovecash.bch.electrum import ElectrumClient
from lovecash.bch.payment import build_uri, qr_png
from lovecash.config import Settings
from lovecash.server.app import create_app

app = typer.Typer(
    help="Performer-first BCH <-> Lovense bridge.",
    no_args_is_help=True,
)
console = Console()


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


@app.command()
def init(config: str = typer.Option("config.yaml", "--config", "-c")) -> None:
    """Interactive setup wizard. Run this first."""
    asyncio.run(_init(config))


async def _init(config: str) -> None:

    console.print(Panel.fit("lovecash setup", style="bold magenta"))
    if await Path(config).exists() and not typer.confirm(
        f"{config} exists. Overwrite?", default=False
    ):
        raise typer.Exit()

    console.print(
        "[dim]Paste your wallet's Master Public Key (starts with 'xpub'). "
        "Find it in Electron Cash under Wallet -> Information.\n"
        "NEVER paste a private key (xprv) or seed phrase — lovecash only "
        "needs your PUBLIC key and can never spend your funds.[/]"
    )
    deriver: XpubDeriver | None = None
    xpub = ""
    while deriver is None:
        xpub = typer.prompt("Your Bitcoin Cash xpub").strip()
        try:
            deriver = XpubDeriver(xpub)
        except XpubError as exc:
            console.print(f"[red]{exc}[/]")

    # Sanity check: confirm the first derived address matches the wallet
    # BEFORE going live, so a wrong-wallet xpub is caught here.
    first = deriver.address(0)
    console.print(f"[dim]Your first receiving address will be:[/] [cyan]{first}[/]")
    if not typer.confirm(
        "Does this match your wallet's first receive address?", default=True
    ):
        console.print(
            "[red]Stop — that xpub is from a different wallet than you "
            "expect. Tips would go somewhere you don't control. Re-run "
            "init with the correct xpub.[/]"
        )
        raise typer.Exit(code=1)

    max_strength = typer.prompt("Max toy strength (0-20)", type=int, default=12)
    max_duration = typer.prompt(
        "Max duration per tip (seconds)", type=float, default=30.0
    )
    host_relay = typer.confirm("Enable the OBS overlay relay?", default=True)

    cfg: dict[str, dict | list[dict]] = {
        "limits": {
            "max_strength": max_strength,
            "max_duration_s": max_duration,
            "min_seconds_between_commands": 0.5,
        },
        "lovense": {"host": "127.0.0.1", "port": 30010, "use_https": True},
        "bch": {
            "xpub": xpub,
            "derivation_branch": 0,
            "gap_limit": 20,
            "rotate_on_payment": True,
            "zeroconf_max_sats": 100000,
            "servers": [
                {"host": "fulcrum.jettscythe.xyz", "port": 50002, "use_ssl": True}
            ],
        },
        "server": {
            "enabled": host_relay,
            "bind_host": "127.0.0.1",
            "bind_port": 8080,
            "relay_token": None,
        },
        "rules": [
            {
                "name": "tease",
                "min_sats": 1000,
                "max_sats": 9999,
                "action": "Vibrate",
                "strength": min(4, max_strength),
                "duration_s": 3,
            },
            {
                "name": "intense",
                "min_sats": 50000,
                "action": "Vibrate",
                "strength": max_strength,
                "duration_s": min(20, max_duration),
            },
        ],
    }
    await Path(config).write_text(yaml.safe_dump(cfg, sort_keys=False))
    console.print(f"[green]Wrote {config}.[/] Next: [bold]lovecash doctor[/]")


@app.command()
def doctor(config: str = typer.Option("config.yaml", "--config", "-c")) -> None:
    """Check everything is wired up before going live."""
    asyncio.run(_doctor(config))


async def _doctor(config: str) -> None:
    from pydantic import ValidationError

    if not await Path(config).exists():
        console.print(
            f"[red]No config at {config}.[/] Run [bold]lovecash init[/] first."
        )
        raise typer.Exit(code=1)

    try:
        settings = Settings.from_yaml(config)
    except ValidationError as exc:
        console.print(f"[red]Your {config} has a problem:[/]")
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"])
            console.print(f"  [yellow]{loc}[/]: {err['msg']}")
        console.print(
            "\n[dim]Tip: each rule must start with '-'. "
            "Run [bold]lovecash init[/] to regenerate a clean "
            "config.[/]"
        )
        raise typer.Exit(code=1) from exc

    table = Table("Check", "Result")
    try:
        d = XpubDeriver(settings.bch.xpub, settings.bch.derivation_branch)
        table.add_row("xpub", f"[green]valid -> {d.address(0)}[/]")
    except XpubError as exc:
        table.add_row("xpub", f"[red]{exc}[/]")

    # 2. Electrum reachability
    for server in settings.bch.server_pool():
        try:
            c = ElectrumClient(
                server.host,
                server.port,
                server.ssl,
            )
            await asyncio.wait_for(c.connect(), timeout=8)
            await c.call("server.ping")
            await c.close()
            table.add_row(f"Electrum server {server.host}", "[green]reachable[/]")
        except Exception as exc:
            table.add_row("Electrum server", f"[red]unreachable: {exc}[/]")

    # 3. Lovense local API + toy online status
    try:
        scheme = "https" if settings.lovense.use_https else "http"
        url = f"{scheme}://{settings.lovense.host}:{settings.lovense.port}"
        async with AsyncClient(verify=False, timeout=4) as hc:
            resp = await hc.get(f"{url}/GetToys")
        data = resp.json().get("data", {})
        online = [t for t in data.values() if t.get("status") == 1]
        if online:
            names = ", ".join(t.get("name", "?") for t in online)
            table.add_row("Lovense Connect", f"[green]{len(online)} toy(s): {names}[/]")
        else:
            table.add_row(
                "Lovense Connect", "[yellow]connected, but no toy online (status=1)[/]"
            )
    except Exception:
        table.add_row(
            "Lovense Connect", "[yellow]not found — open the Lovense app and enable "
        )

    console.print(table)


@app.command()
def serve(
    config: str = typer.Option("config.yaml", "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run the hosted relay + OBS overlay (needs the 'server' extra)."""
    _setup_logging(verbose)
    import uvicorn

    settings = Settings.from_yaml(config)
    host, port = settings.server.bind_host, settings.server.bind_port
    app_instance = create_app(settings)  # raises early if misconfigured
    display_host = "localhost" if host == "0.0.0.0" else host
    console.print(
        Panel.fit(
            f"OBS Browser Source URL:\n[bold cyan]http://{display_host}:{port}/overlay[/]",
            title="Add this to OBS",
            style="green",
        )
    )
    uvicorn.run(app_instance, host=host, port=port)


@app.command()
def qr(
    config: str = typer.Option("config.yaml", "--config", "-c"),
    amount: float = typer.Option(None, "--amount"),
    index: int = typer.Option(0, "--index", help="Derivation index"),
    out: str = typer.Option("tip-qr.png", "--out", "-o"),
) -> None:
    """Save a tipping QR code to a file (for thumbnails, panels, etc.)."""
    asyncio.run(_qr(config, amount, index, out))


async def _qr(config: str, amount: float | None, index: int, out: str) -> None:
    settings = Settings.from_yaml(config)
    deriver = XpubDeriver(settings.bch.xpub, settings.bch.derivation_branch)
    uri = build_uri(deriver.address(index), amount_bch=amount)
    await Path(out).write_bytes(qr_png(uri))
    console.print(f"[green]Saved {out}[/]  ({uri})")


@app.command()
def scripthash(address: str) -> None:
    """Print the Electrum scripthash for an address (debugging)."""

    console.print(to_scripthash(address))
