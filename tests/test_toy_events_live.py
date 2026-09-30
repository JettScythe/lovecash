"""Live Lovense game-mode socket check — needs the Lovense app running
with GAME MODE ON and a toy connected. Skipped by default; run with:

    uv run pytest -m integration tests/test_toy_events_live.py -v
"""

import asyncio

import pytest

from lovecash.config import LovenseConfig
from lovecash.lovense.eventsocket import LovenseEventSocket

pytestmark = pytest.mark.integration


async def test_game_mode_socket_streams_events():
    sock = LovenseEventSocket(LovenseConfig())
    gen = sock.events()
    try:
        msg = await asyncio.wait_for(anext(gen), timeout=10)
    finally:
        await gen.aclose()
        await sock.close()
    assert isinstance(msg, dict) and "type" in msg
