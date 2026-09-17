"""Known Lovense toys: their primary action and sensible rule defaults.

Entries are sourced from Lovense's official Standard API action list
(Vibrate, Rotate, Pump, Thrusting, Fingering, Suction, Depth, Oscillate,
Stop — developer.lovense.com/docs/standard-solutions/standard-api.html)
and the published product lineup. Keys are the lowercase name the toy
reports via /GetToys (e.g. "lush 3", "solace pro"); the confirmed
entries (Solace line) follow exactly that convention.

Hardware confirmation is still welcome — if a real unit reports a
different name string than the key here, fix the key. Unknown toys fall
back to asking the action directly in `init`, so a missing entry is
never a failure.

Dual-channel toys (Nora, Max 2, Osci 3, Ridge, Gravity) default to the
All action so tips drive every channel at once — a single-channel
default would silently waste half the toy. Performers can still
hand-edit rules to a single channel or use extra_actions for mixed
strengths.
"""

from dataclasses import dataclass
from enum import StrEnum

from lovecash.models import Action


class ToyCategory(StrEnum):
    VIBRATOR = "vibrator"
    STROKER = "stroker"
    ROTATOR = "rotator"
    PUMP = "pump"
    OSCILLATOR = "oscillator"
    FINGERING = "fingering"
    SUCTION = "suction"


@dataclass(frozen=True)
class ToyProfile:
    name: str
    action: Action
    category: ToyCategory


KNOWN_TOYS: dict[str, ToyProfile] = {
    # Vibrators
    "lush": ToyProfile("Lush", Action.VIBRATE, ToyCategory.VIBRATOR),
    "lush 2": ToyProfile("Lush 2", Action.VIBRATE, ToyCategory.VIBRATOR),
    "lush 3": ToyProfile("Lush 3", Action.VIBRATE, ToyCategory.VIBRATOR),
    "lush 4": ToyProfile("Lush 4", Action.VIBRATE, ToyCategory.VIBRATOR),
    "lush mini": ToyProfile("Lush Mini", Action.VIBRATE, ToyCategory.VIBRATOR),
    "lush anal": ToyProfile("Lush Anal", Action.VIBRATE, ToyCategory.VIBRATOR),
    "hush": ToyProfile("Hush", Action.VIBRATE, ToyCategory.VIBRATOR),
    "hush 2": ToyProfile("Hush 2", Action.VIBRATE, ToyCategory.VIBRATOR),
    "domi": ToyProfile("Domi", Action.VIBRATE, ToyCategory.VIBRATOR),
    "domi 2": ToyProfile("Domi 2", Action.VIBRATE, ToyCategory.VIBRATOR),
    "ambi": ToyProfile("Ambi", Action.VIBRATE, ToyCategory.VIBRATOR),
    "edge": ToyProfile("Edge", Action.VIBRATE, ToyCategory.VIBRATOR),
    "edge 2": ToyProfile("Edge 2", Action.VIBRATE, ToyCategory.VIBRATOR),
    "diamo": ToyProfile("Diamo", Action.VIBRATE, ToyCategory.VIBRATOR),
    "gush": ToyProfile("Gush", Action.VIBRATE, ToyCategory.VIBRATOR),
    "gush 2": ToyProfile("Gush 2", Action.VIBRATE, ToyCategory.VIBRATOR),
    "calor": ToyProfile("Calor", Action.VIBRATE, ToyCategory.VIBRATOR),
    "dolce": ToyProfile("Dolce", Action.VIBRATE, ToyCategory.VIBRATOR),
    "ferri": ToyProfile("Ferri", Action.VIBRATE, ToyCategory.VIBRATOR),
    "hyphy": ToyProfile("Hyphy", Action.VIBRATE, ToyCategory.VIBRATOR),
    "exomoon": ToyProfile("Exomoon", Action.VIBRATE, ToyCategory.VIBRATOR),
    "gemini": ToyProfile("Gemini", Action.VIBRATE, ToyCategory.VIBRATOR),
    "lapis": ToyProfile("Lapis", Action.VIBRATE, ToyCategory.VIBRATOR),
    "mission": ToyProfile("Mission", Action.VIBRATE, ToyCategory.VIBRATOR),
    "mission 2": ToyProfile("Mission 2", Action.VIBRATE, ToyCategory.VIBRATOR),
    # Dual-channel vibrators (vibrate + rotate/pump) -> All
    "nora": ToyProfile("Nora", Action.ALL, ToyCategory.VIBRATOR),
    "ridge": ToyProfile("Ridge", Action.ALL, ToyCategory.VIBRATOR),
    "max": ToyProfile("Max", Action.ALL, ToyCategory.VIBRATOR),
    "max 2": ToyProfile("Max 2", Action.ALL, ToyCategory.VIBRATOR),
    "osci 3": ToyProfile("Osci 3", Action.ALL, ToyCategory.VIBRATOR),
    # Thrusting strokers / thrusters
    "solace pro": ToyProfile("Solace Pro", Action.THRUSTING, ToyCategory.STROKER),
    "solace": ToyProfile("Solace", Action.THRUSTING, ToyCategory.STROKER),
    # Gravity thrusts AND vibrates -> All, with the longer stroker ladder
    "gravity": ToyProfile("Gravity", Action.ALL, ToyCategory.STROKER),
    "vulse": ToyProfile("Vulse", Action.THRUSTING, ToyCategory.STROKER),
    # Oscillating G-spot toys (single channel)
    "osci": ToyProfile("Osci", Action.OSCILLATE, ToyCategory.OSCILLATOR),
    "osci 2": ToyProfile("Osci 2", Action.OSCILLATE, ToyCategory.OSCILLATOR),
    # Come-hither motion
    "flexer": ToyProfile("Flexer", Action.FINGERING, ToyCategory.FINGERING),
    # Clitoral suction
    "tenera": ToyProfile("Tenera", Action.SUCTION, ToyCategory.SUCTION),
    "tenera 2": ToyProfile("Tenera 2", Action.SUCTION, ToyCategory.SUCTION),
}

# Per-category default rule ladder. strength clamped to max_strength in
# onboard.build_rules AND to the action's hardware ceiling (Pump/Depth
# are 0-3) by the controller before anything reaches the device.
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
    # Pump hardware ceiling is 3 — never ladder above it.
    ToyCategory.PUMP: [
        {
            "name": "tease",
            "min_sats": 1000,
            "max_sats": 9999,
            "strength": 1,
            "duration_s": 3,
        },
        {
            "name": "squeeze",
            "min_sats": 10000,
            "max_sats": 49999,
            "strength": 2,
            "duration_s": 6,
        },
        {"name": "intense", "min_sats": 50000, "strength": 3, "duration_s": 10},
    ],
    ToyCategory.OSCILLATOR: [
        {
            "name": "tease",
            "min_sats": 1000,
            "max_sats": 9999,
            "strength": 4,
            "duration_s": 3,
        },
        {
            "name": "pulse",
            "min_sats": 10000,
            "max_sats": 49999,
            "strength": 10,
            "duration_s": 8,
        },
        {"name": "intense", "min_sats": 50000, "strength": 18, "duration_s": 15},
    ],
    ToyCategory.FINGERING: [
        {
            "name": "tease",
            "min_sats": 1000,
            "max_sats": 9999,
            "strength": 4,
            "duration_s": 4,
        },
        {
            "name": "stroke",
            "min_sats": 10000,
            "max_sats": 49999,
            "strength": 10,
            "duration_s": 10,
        },
        {"name": "intense", "min_sats": 50000, "strength": 16, "duration_s": 15},
    ],
    ToyCategory.SUCTION: [
        {
            "name": "tease",
            "min_sats": 1000,
            "max_sats": 9999,
            "strength": 3,
            "duration_s": 3,
        },
        {
            "name": "draw",
            "min_sats": 10000,
            "max_sats": 49999,
            "strength": 8,
            "duration_s": 6,
        },
        {"name": "intense", "min_sats": 50000, "strength": 14, "duration_s": 10},
    ],
}
