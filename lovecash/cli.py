from __future__ import annotations

import asyncio
import logging

import typer
import yaml
from httpx import AsyncClient
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

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


async def _detect_toys() -> list[tuple[str, str]]:
    """Return [(toy_id, name), ...] of online toys from Lovense Connect."""
    from lovecash.config import LovenseConfig

    cfg = LovenseConfig()
    scheme = "https" if cfg.use_https else "http"
    url = f"{scheme}://{cfg.host}:{cfg.port}/GetToys"
    try:
        async with AsyncClient(verify=False, timeout=4) as hc:
            resp = await hc.get(url)
        data = resp.json().get("data", {})
        return [
            (tid, t.get("name", "Unknown"))
            for tid, t in data.items()
            if t.get("status") == 1
        ]
    except Exception:
        return []


def _prompt_action(label: str):
    from lovecash.lovense.toys import parse_action

    while True:
        raw = typer.prompt(
            f"{label} (Vibrate / Thrusting / Rotate / Pump / Depth)",
            default="Vibrate",
        )
        try:
            return parse_action(raw)
        except ValueError:
            console.print("[red]Unknown action. Pick one of the listed.[/]")


def _build_rules(
    action,
    category,
    toy_id: str | None,
    toy_label: str,
    multi: bool,
    max_strength: int,
    max_duration: float,
) -> list[dict]:
    from lovecash.lovense.toys import CATEGORY_RULES

    rules: list[dict] = []
    for r in CATEGORY_RULES[category]:
        rule: dict = {
            "name": f"{toy_label}-{r['name']}" if multi else r["name"],
            "min_sats": r["min_sats"],
            "action": action.value,
            "strength": min(r["strength"], max_strength),
            "duration_s": min(float(r["duration_s"]), max_duration),
        }
        if "max_sats" in r:
            rule["max_sats"] = r["max_sats"]
        if multi and toy_id is not None:
            rule["toy"] = toy_id
        rules.append(rule)
    return rules


async def _init(config: str) -> None:
    from importlib.resources import files

    from anyio import Path

    from lovecash.bch.derive import XpubDeriver, XpubError
    from lovecash.config import Settings
    from lovecash.lovense.toys import KNOWN_TOYS, ToyCategory

    console.print(Panel.fit("lovecash setup", style="bold magenta"))
    if await Path(config).exists() and not typer.confirm(
        f"{config} exists. Overwrite?", default=False
    ):
        raise typer.Exit()

    # --- xpub with the index-0 wallet confirmation ---
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

    # --- toy limits ---
    max_strength = typer.prompt("Max toy strength (0-20)", type=int, default=12)
    max_duration = typer.prompt(
        "Max duration per tip (seconds)", type=float, default=30.0
    )

    # --- detect toys and build per-toy rules ---
    console.print("[dim]Looking for connected Lovense toys...[/]")
    detected = await _detect_toys()
    toy_specs: list[dict] = []
    all_rules: list[dict] = []

    if not detected:
        console.print(
            "[yellow]No toys detected (is the Lovense Connect app running "
            "with Game Mode on?). Setting up rules manually — you can run "
            "init again later once your toy is connected.[/]"
        )
        action = _prompt_action("What does your toy do?")
        all_rules = _build_rules(
            action,
            ToyCategory.VIBRATOR,
            None,
            "",
            False,
            max_strength,
            max_duration,
        )
    else:
        multi = len(detected) > 1
        console.print(f"[green]Detected {len(detected)} toy(s).[/]")
        for toy_id, raw_name in detected:
            profile = KNOWN_TOYS.get(raw_name.lower())
            if profile is None:
                console.print(
                    f"[yellow]'{raw_name}' isn't in the known-toy list "
                    f"yet — please tell me what it does.[/]"
                )
                action = _prompt_action(f"Action for {raw_name}")
                category = ToyCategory.VIBRATOR
            else:
                action = profile.action
                category = profile.category
                console.print(f"  [cyan]{raw_name}[/] -> {action.value}")
            all_rules.extend(
                _build_rules(
                    action,
                    category,
                    toy_id,
                    raw_name,
                    multi,
                    max_strength,
                    max_duration,
                )
            )
            if multi:
                toy_specs.append({"toy_id": toy_id})

    relay_enabled = typer.confirm("Enable the OBS overlay relay?", default=True)

    # --- render the template ---

    template = (files("lovecash") / "config.template.yaml").read_text()
    rendered = (
        template.replace("{{ xpub }}", xpub)
        .replace("{{ max_strength }}", str(max_strength))
        .replace("{{ max_duration_s }}", str(max_duration))
        .replace("{{ relay_enabled }}", "true" if relay_enabled else "false")
    )

    rules_yaml = yaml.safe_dump({"rules": all_rules}, sort_keys=False).strip()
    rendered = rendered.replace("{{ rules }}", rules_yaml)

    toys_yaml = ""
    if toy_specs:
        toys_yaml = yaml.safe_dump({"toys": toy_specs}, sort_keys=False).strip()
    rendered = rendered.replace("{{ toys }}", toys_yaml)

    # --- validate BEFORE writing ---
    try:
        Settings.model_validate(yaml.safe_load(rendered))
    except Exception as exc:
        console.print(
            "[red]Internal error: the generated config failed validation. "
            "This is a bug in the template/toy table, not your input.[/]"
        )
        console.print(f"[dim]{exc}[/]")
        raise typer.Exit(code=1) from exc

    await Path(config).write_text(rendered)
    console.print(f"[green]Wrote {config}.[/] Next: [bold]lovecash doctor[/]")


@app.command()
def doctor(config: str = typer.Option("config.yaml", "--config", "-c")) -> None:
    """Check everything is wired up before going live."""
    asyncio.run(_doctor(config))


async def _doctor(config: str) -> None:
    from anyio import Path
    from pydantic import ValidationError

    from lovecash.bch.derive import XpubDeriver, XpubError
    from lovecash.bch.electrum import ElectrumClient
    from lovecash.config import Settings

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
    from lovecash.config import Settings
    from lovecash.server.app import create_app

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
    from anyio import Path

    from lovecash.bch.derive import XpubDeriver
    from lovecash.bch.payment import build_uri, qr_png
    from lovecash.config import Settings

    settings = Settings.from_yaml(config)
    deriver = XpubDeriver(settings.bch.xpub, settings.bch.derivation_branch)
    uri = build_uri(deriver.address(index), amount_bch=amount)
    await Path(out).write_bytes(qr_png(uri))
    console.print(f"[green]Saved {out}[/]  ({uri})")


@app.command()
def scripthash(address: str) -> None:
    """Print the Electrum scripthash for an address (debugging)."""

    from lovecash.bch.cashaddr import to_scripthash

    console.print(to_scripthash(address))
