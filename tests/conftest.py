# tests/conftest.py
from __future__ import annotations

import pytest

from lovecash.config import (
    BchConfig,
    Limits,
    LovenseConfig,
    Playback,
    ServerConfig,
    Settings,
)
from lovecash.models import Action, TipRule

ADDR = "bitcoincash:qpm2qsznhks23z7629mms6s4cwef74vcwvy22gdx6a"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        limits=Limits(
            max_strength=12,
            max_duration_s=30,
            min_seconds_between_commands=0,
            playback=Playback.OVERRIDE,
        ),
        lovense=LovenseConfig(),
        bch=BchConfig(address=ADDR),
        server=ServerConfig(),
        rules=[
            TipRule(
                name="tease",
                min_sats=1000,
                max_sats=9999,
                action=Action.VIBRATE,
                strength=4,
                duration_s=3,
            ),
            TipRule(
                name="intense",
                min_sats=50000,
                min_confirmations=1,
                action=Action.VIBRATE,
                strength=12,
                duration_s=20,
            ),
        ],
    )
