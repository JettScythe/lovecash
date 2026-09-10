"""Shared onboarding logic: used by both the CLI wizard (`lovecash init`)
and the web setup wizard (/setup). Keeps the two surfaces in lockstep."""

from importlib.resources import files

import yaml
from httpx import AsyncClient

from lovecash.bch.derive import XpubDeriver
from lovecash.config import LovenseConfig, Settings
from lovecash.lovense.toys import CATEGORY_RULES, KNOWN_TOYS, ToyCategory
from lovecash.models import Action


async def detect_toys(cfg: LovenseConfig | None = None) -> list[tuple[str, str]]:
    """Return [(toy_id, name), ...] of online toys from Lovense Connect."""
    cfg = cfg or LovenseConfig()
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


def toy_defaults(name: str) -> tuple[Action, ToyCategory] | None:
    """(action, category) for a known toy name, else None (ask the user)."""
    profile = KNOWN_TOYS.get(name.lower())
    return (profile.action, profile.category) if profile else None


def build_rules(
    action: Action,
    category: ToyCategory,
    toy_id: str | None,
    toy_label: str,
    multi: bool,
    max_strength: int,
    max_duration: float,
) -> list[dict]:
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


def render_config(
    xpub: str,
    max_strength: int,
    max_duration: float,
    relay_enabled: bool,
    rules: list[dict],
    toys: list[dict],
) -> str:
    """Render config.template.yaml and validate the result. Raises on
    an invalid xpub or a template/toy-table bug (ValidationError)."""
    XpubDeriver(xpub)  # raises XpubError on bad/private key
    rendered = (
        (files("lovecash") / "config.template.yaml")
        .read_text()
        .replace("{{ xpub }}", xpub)
        .replace("{{ max_strength }}", str(max_strength))
        .replace("{{ max_duration_s }}", str(max_duration))
        .replace("{{ relay_enabled }}", "true" if relay_enabled else "false")
    )
    rules_yaml = yaml.safe_dump({"rules": rules}, sort_keys=False).strip()
    rendered = rendered.replace("{{ rules }}", rules_yaml)
    # `{{ toys }}` sits indented under `lovense:` — continuation lines of
    # the list need the same +2 indent or the yaml block breaks.
    toys_yaml = ""
    if toys:
        dumped = yaml.safe_dump({"toys": toys}, sort_keys=False).strip()
        toys_yaml = dumped.replace("\n", "\n  ")
    rendered = rendered.replace("{{ toys }}", toys_yaml)
    Settings.model_validate(yaml.safe_load(rendered))
    return rendered
