import asyncio
import logging

import typer
import yaml
from anyio import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from lovecash.config import Settings
from lovecash.core.orchestrator import Orchestrator

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
    from lovecash.bch.cashaddr import decode

    console.print(Panel.fit("lovecash setup", style="bold magenta"))
    if Path(config).exists() and not typer.confirm(
        f"{config} exists. Overwrite?", default=False
    ):
        raise typer.Exit()

    while True:
        address = typer.prompt("Your Bitcoin Cash receiving address").strip()
        try:
            decode(address)
            break
        except ValueError:
            console.print(
                "[red]That doesn't look like a valid BCH address. Try again.[/]"
            )

    console.print(
        "[dim]This address only RECEIVES. lovecash never sees your private keys.[/]"
    )
    max_strength = typer.prompt("Max vibration strength (0-20)", type=int, default=12)
    max_duration = typer.prompt(
        "Max duration per tip (seconds)", type=float, default=30.0
    )
    host_relay = typer.confirm("Enable the OBS overlay relay?", default=True)

    cfg = {
        "limits": {
            "max_strength": max_strength,
            "max_duration_s": max_duration,
            "min_seconds_between_commands": 0.5,
        },
        "lovense": {"host": "127.0.0.1", "port": 30010, "use_https": True},
        "bch": {
            "address": address,
            "electrum_host": "fulcrum.fountainhead.cash",
            "electrum_port": 50002,
            "electrum_ssl": True,
            "zeroconf_max_sats": 100000,
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
                "min_confirmations": 1,
                "action": "Vibrate",
                "strength": max_strength,
                "duration_s": min(20, max_duration),
            },
        ],
    }
    Path(config).write_text(yaml.safe_dump(cfg, sort_keys=False))
    console.print(f"[green]Wrote {config}.[/] Next: [bold]lovecash doctor[/]")


@app.command()
def doctor(config: str = typer.Option("config.yaml", "--config", "-c")) -> None:
    """Check everything is wired up before going live."""
    asyncio.run(_doctor(config))


async def _doctor(config: str) -> None:
    from pydantic import ValidationError

    from lovecash.bch.cashaddr import to_scripthash
    from lovecash.bch.electrum import ElectrumClient

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
    # ... rest of the function unchanged (address / electrum / lovense checks)
    settings = Settings.from_yaml(config)

    # 1. Address
    try:
        to_scripthash(settings.bch.address)
        table.add_row("BCH address", "[green]valid[/]")
    except Exception as exc:
        table.add_row("BCH address", f"[red]invalid: {exc}[/]")

    # 2. Electrum reachability
    try:
        c = ElectrumClient(
            settings.bch.electrum_host,
            settings.bch.electrum_port,
            settings.bch.electrum_ssl,
        )
        await asyncio.wait_for(c.connect(), timeout=8)
        await c.call("server.ping")
        await c.close()
        table.add_row("Electrum server", "[green]reachable[/]")
    except Exception as exc:
        table.add_row("Electrum server", f"[red]unreachable: {exc}[/]")

    # 3. Lovense local API
    try:
        import httpx

        scheme = "https" if settings.lovense.use_https else "http"
        url = f"{scheme}://{settings.lovense.host}:{settings.lovense.port}"
        async with httpx.AsyncClient(verify=False, timeout=4) as hc:
            await hc.get(f"{url}/GetToys")
        table.add_row("Lovense Connect", "[green]responding[/]")
    except Exception:
        table.add_row(
            "Lovense Connect",
            "[yellow]not found — open the Lovense app and enable "
            "Game Mode / Connect[/]",
        )

    console.print(table)


@app.command()
def run(
    config: str = typer.Option("config.yaml", "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    skip_check: bool = typer.Option(False, "--skip-check"),
) -> None:
    """Run the local bridge."""
    _setup_logging(verbose)
    if not Path(config).exists():
        console.print("[red]No config found.[/] Run [bold]lovecash init[/] first.")
        raise typer.Exit(code=1)
    if not skip_check:
        asyncio.run(_doctor(config))
        settings = Settings.from_yaml(config)
        orch = Orchestrator(settings)

    async def _main() -> None:
        try:
            await orch.run()
        except (KeyboardInterrupt, asyncio.CancelledError):
            console.print("[bold red]Panic stop — shutting down.[/]")
            await orch.shutdown()

    asyncio.run(_main())


@app.command()
def serve(
    config: str = typer.Option("config.yaml", "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run the hosted relay + OBS overlay (needs the 'server' extra)."""
    _setup_logging(verbose)
    import uvicorn

    from lovecash.server.app import create_app

    settings = Settings.from_yaml(config)
    host, port = settings.server.bind_host, settings.server.bind_port
    app_instance = create_app(settings)  # raises early if misconfigured
    console.print(
        Panel.fit(
            f"OBS Browser Source URL:\n[bold cyan]http://{host}:{port}/overlay[/]",
            title="Add this to OBS",
            style="green",
        )
    )
    uvicorn.run(app_instance, host=host, port=port)


@app.command()
def qr(
    config: str = typer.Option("config.yaml", "--config", "-c"),
    amount: float = typer.Option(None, "--amount"),
    out: str = typer.Option("tip-qr.png", "--out", "-o"),
) -> None:
    """Save a tipping QR code to a file (for thumbnails, panels, etc.)."""
    from lovecash.bch.payment import build_uri, qr_png

    settings = Settings.from_yaml(config)
    uri = build_uri(settings.bch.address, amount_bch=amount)
    Path(out).write_bytes(qr_png(uri))
    console.print(f"[green]Saved {out}[/]  ({uri})")


@app.command()
def scripthash(address: str) -> None:
    """Print the Electrum scripthash for an address (debugging)."""
    from lovecash.bch.cashaddr import to_scripthash

    console.print(to_scripthash(address))


if __name__ == "main":
    app()
