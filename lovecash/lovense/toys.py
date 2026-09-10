"""Known Lovense toys: their primary action and sensible rule defaults.

ONLY include toys whose API action has been CONFIRMED against a real
device. An unverified entry risks writing a rule that silently does
nothing. Unknown toys fall back to asking the action directly in `init`.

Keys are the lowercase name the toy reports via /GetToys — confirm the
exact string on a real unit before adding an entry.
"""

from dataclasses import dataclass
from enum import StrEnum

from lovecash.models import Action


class ToyCategory(StrEnum):
    VIBRATOR = "vibrator"
    STROKER = "stroker"
    ROTATOR = "rotator"
    PUMP = "pump"


@dataclass(frozen=True)
class ToyProfile:
    name: str
    action: Action
    category: ToyCategory


# Add entries only after confirming the action works via /command on a
# real unit, keyed on what /GetToys actually reports as the name.
KNOWN_TOYS: dict[str, ToyProfile] = {
    "solace pro": ToyProfile("Solace Pro", Action.THRUSTING, ToyCategory.STROKER),
    "solace": ToyProfile("Solace", Action.THRUSTING, ToyCategory.STROKER),
    # Confirmed-expected but UNTESTED — uncomment after verifying on device:
    # "lush 4": ToyProfile("Lush 4", Action.VIBRATE, ToyCategory.VIBRATOR),
    # "hush 2": ToyProfile("Hush 2", Action.VIBRATE, ToyCategory.VIBRATOR),
    # "nora":   ToyProfile("Nora", Action.ROTATE, ToyCategory.ROTATOR),
    # "max 2":  ToyProfile("Max 2", Action.PUMP, ToyCategory.PUMP),
}

# Per-category default rule ladder. strength clamped to max_strength in init.
CATEGORY_RULES: dict[ToyCategory, list[dict]] = {
    ToyCategory.VIBRATOR: [
        {
            "name": "tease",
            "min_sats": 1000,
            "max_sats": 9999,
            "strength": 4,
            "duration_s": 3,
        },
        {
            "name": "buzz",
            "min_sats": 10000,
            "max_sats": 49999,
            "strength": 10,
            "duration_s": 8,
        },
        {"name": "intense", "min_sats": 50000, "strength": 18, "duration_s": 15},
    ],
    ToyCategory.STROKER: [
        {
            "name": "tease",
            "min_sats": 1000,
            "max_sats": 9999,
            "strength": 4,
            "duration_s": 5,
        },
        {
            "name": "build",
            "min_sats": 10000,
            "max_sats": 49999,
            "strength": 10,
            "duration_s": 12,
        },
        {"name": "intense", "min_sats": 50000, "strength": 18, "duration_s": 20},
    ],
    ToyCategory.ROTATOR: [
        {
            "name": "tease",
            "min_sats": 1000,
            "max_sats": 9999,
            "strength": 4,
            "duration_s": 4,
        },
        {
            "name": "spin",
            "min_sats": 10000,
            "max_sats": 49999,
            "strength": 10,
            "duration_s": 10,
        },
        {"name": "intense", "min_sats": 50000, "strength": 16, "duration_s": 15},
    ],
    ToyCategory.PUMP: [
        {
            "name": "tease",
            "min_sats": 1000,
            "max_sats": 9999,
            "strength": 3,
            "duration_s": 3,
        },
        {
            "name": "squeeze",
            "min_sats": 10000,
            "max_sats": 49999,
            "strength": 8,
            "duration_s": 6,
        },
        {"name": "intense", "min_sats": 50000, "strength": 14, "duration_s": 10},
    ],
}
