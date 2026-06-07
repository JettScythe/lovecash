from pathlib import Path

import yaml

from lovecash.config import BchConfig, Limits, PricingConfig


def _rendered_template() -> dict:
    text = (Path("lovecash") / "config.template.yaml").read_text()

    sample_rules = [
        {
            "name": "tease",
            "min_sats": 5000,
            "action": "Vibrate",
            "strength": 4,
            "duration_s": 20.0,
        },
        {
            "name": "intense",
            "min_sats": 50000,
            "max_sats": 200000,
            "action": "Vibrate",
            "strength": 12,
            "duration_s": 30.0,
        },
    ]
    rules_yaml = yaml.safe_dump({"rules": sample_rules}, sort_keys=False).strip()
    toys_yaml = yaml.safe_dump({"toys": []}, sort_keys=False).strip()

    for ph, val in {
        "{{ xpub }}": "xpub6DF5GApwf8FAAoTTwY6Gk2ZXC1uM6kCqqZBBTEC2Bc6"
        "ELxQn6ftHxexXxr8RsQpka7racgE7QbVs4JBdCXn7XL63LEF8tAC6u6KrT5eeseS",
        "{{ max_strength }}": "12",
        "{{ max_duration_s }}": "30.0",
        "{{ relay_enabled }}": "true",
        "{{ rules }}": rules_yaml,  # ← matches the template marker
        "{{ toys }}": toys_yaml,  # ← matches the template marker
    }.items():
        text = text.replace(ph, val)

    return yaml.safe_load(text)


def test_template_covers_every_bch_field():
    cfg = _rendered_template()["bch"]
    for field in BchConfig.model_fields:
        assert field in cfg, f"bch.{field} missing from config template"


def test_template_covers_every_limits_field():
    cfg = _rendered_template()["limits"]
    for field in Limits.model_fields:
        assert field in cfg, f"limits.{field} missing from config template"


def test_template_covers_every_pricing_field():
    cfg = _rendered_template()["bch"]["pricing"]
    for field in PricingConfig.model_fields:
        assert field in cfg, f"pricing.{field} missing from config template"


def test_rendered_template_validates():
    from lovecash.config import Settings

    Settings.model_validate(_rendered_template())  # must parse cleanly
