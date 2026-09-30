"""Toy events pipeline: event models, EventRule matching, socket client,
source routing, orchestrator wiring (issue #20 piece 1)."""

import pytest
from pydantic import TypeAdapter, ValidationError

from lovecash.models import Action, EventRule, ToyCommand, ToyEventKind
from lovecash.triggers.events import (
    PaymentTrigger,
    ToyEventTrigger,
    TriggerEvent,
)


def test_trigger_union_discriminates():
    trig = ToyEventTrigger(event=ToyEventKind.SHAKE, toy_id="abc")
    assert trig.kind == "toy_event"
    assert trig.value is None
    assert trig.button_index is None

    adapter = TypeAdapter(TriggerEvent)
    payment = adapter.validate_python(
        {
            "kind": "payment",
            "source_id": "s",
            "txid": "t",
            "amount_sats": 1,
            "confirmations": 0,
        }
    )
    assert isinstance(payment, PaymentTrigger)
    toy = adapter.validate_python(
        {"kind": "toy_event", "event": "shake", "toy_id": "abc"}
    )
    assert isinstance(toy, ToyEventTrigger)
    assert toy.event is ToyEventKind.SHAKE


def _depth(value, toy_id="aaa"):
    return ToyEventTrigger(
        event=ToyEventKind.DEPTH_CHANGED, toy_id=toy_id, value=value
    )


def test_event_rule_rejects_narrowed_band_on_shake():
    with pytest.raises(ValidationError, match="band"):
        EventRule(
            name="x", event=ToyEventKind.SHAKE, duration_s=1, min_value=5
        )


def test_event_rule_rejects_button_index_on_depth():
    with pytest.raises(ValidationError, match="button_index"):
        EventRule(
            name="x", event=ToyEventKind.DEPTH_CHANGED, duration_s=1,
            button_index=1,
        )


def test_event_rule_rejects_inverted_band():
    with pytest.raises(ValidationError, match="min_value"):
        EventRule(
            name="x", event=ToyEventKind.DEPTH_CHANGED, duration_s=1,
            min_value=10, max_value=5,
        )


def test_event_rule_matches_and_to_command():
    rule = EventRule(
        name="deep",
        event=ToyEventKind.DEPTH_CHANGED,
        action=Action.VIBRATE,
        strength=9,
        duration_s=4,
        min_value=5,
        max_value=10,
        source_toy="aaa",
        toy="bbb",
    )
    assert rule.matches(_depth(7)) is True
    assert rule.matches(_depth(12)) is False
    assert rule.matches(_depth(7, toy_id="other")) is False
    cmd = rule.to_command()
    assert isinstance(cmd, ToyCommand)
    assert cmd.action is Action.VIBRATE
    assert cmd.strength == 9
    assert cmd.duration_s == 4


def _engine():
    from lovecash.engine.rules import RulesEngine

    return RulesEngine(
        [],
        event_rules=[
            EventRule(
                name="tease", event=ToyEventKind.DEPTH_CHANGED, duration_s=2,
                min_value=1, max_value=10,
            ),
            EventRule(
                name="intense", event=ToyEventKind.DEPTH_CHANGED, duration_s=2,
                min_value=11, max_value=20,
            ),
            EventRule(name="shaker", event=ToyEventKind.SHAKE, duration_s=2,
                      toy="t2"),
            EventRule(
                name="button1", event=ToyEventKind.BUTTON_PRESSED, duration_s=2,
                button_index=1,
            ),
        ],
    )


def _fired_names(engine, event):
    return [cmd for cmd, _ in engine.resolve_event(event)]


def test_resolve_event_fires_on_band_entry_only():
    engine = _engine()
    assert len(engine.resolve_event(_depth(5))) == 1  # tease enters
    assert engine.resolve_event(_depth(7)) == []  # still in band: no refire
    intense = engine.resolve_event(_depth(15))
    assert len(intense) == 1  # intense enters
    assert len(engine.resolve_event(_depth(3))) == 1  # tease re-enters


def test_resolve_event_tier_and_target():
    engine = _engine()
    fired = engine.resolve_event(_depth(15))
    assert len(fired) == 1
    cmd, target = fired[0]
    assert target is None  # rule's toy is None -> all toys
    assert cmd.duration_s == 2


def test_resolve_event_shake_fires_every_time():
    engine = _engine()
    shake = ToyEventTrigger(event=ToyEventKind.SHAKE, toy_id="zzz")
    for _ in range(2):
        fired = engine.resolve_event(shake)
        assert len(fired) == 1
        assert fired[0][1] == "t2"  # rule targets toy t2


def test_resolve_event_button_index_filter():
    engine = _engine()
    press0 = ToyEventTrigger(
        event=ToyEventKind.BUTTON_PRESSED, toy_id="zzz", button_index=0
    )
    press1 = ToyEventTrigger(
        event=ToyEventKind.BUTTON_PRESSED, toy_id="zzz", button_index=1
    )
    assert engine.resolve_event(press0) == []
    assert len(engine.resolve_event(press1)) == 1


def test_resolve_event_missing_value_no_crash():
    engine = _engine()
    assert engine.resolve_event(_depth(None)) == []  # no fire, no exception
    assert len(engine.resolve_event(_depth(5))) == 1  # edge was out-of-band


# --- Task 4: LovenseEventSocket -------------------------------------------

import asyncio
import json

from lovecash.config import LovenseConfig
from lovecash.lovense.eventsocket import LovenseEventSocket


class FakeSocket:
    """Stand-in for a websockets client connection."""

    def __init__(self) -> None:
        self.sent: list = []
        self.incoming: asyncio.Queue = asyncio.Queue()
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def feed(self, frame):
        self.incoming.put_nowait(
            frame if isinstance(frame, str) else json.dumps(frame)
        )

    def drop(self):
        self.incoming.put_nowait(ConnectionError("dropped"))

    async def recv(self):
        item = await self.incoming.get()
        if isinstance(item, Exception):
            raise item
        return item

    async def send(self, payload):
        self.sent.append(payload)

    async def close(self):
        self.closed = True


def _factory(sockets):
    calls = []

    def connect(url):
        calls.append(url)
        return sockets[min(len(calls), len(sockets)) - 1]

    return connect, calls


async def _wait_for(pred, timeout=1.0):
    async def poll():
        while not pred():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(poll(), timeout)


def test_socket_url_derivation():
    assert (
        LovenseEventSocket.url_for(LovenseConfig(use_https=True))
        == "wss://127-0-0-1.lovense.club:30010/v1"
    )
    assert (
        LovenseEventSocket.url_for(LovenseConfig(use_https=False))
        == "ws://127.0.0.1:30010/v1"
    )


async def test_socket_sends_access_first():
    ws = FakeSocket()
    connect, _ = _factory([ws])
    sock = LovenseEventSocket(LovenseConfig(), connect=connect)
    ws.feed({"type": "shake", "toyId": "t1"})
    gen = sock.events()
    assert (await asyncio.wait_for(anext(gen), 1))["type"] == "shake"
    assert json.loads(ws.sent[0]) == {
        "type": "access",
        "data": {"appName": "lovecash"},
    }
    await gen.aclose()


async def test_socket_answers_server_ping_with_pong():
    ws = FakeSocket()
    connect, _ = _factory([ws])
    sock = LovenseEventSocket(LovenseConfig(), connect=connect)
    ws.feed({"type": "ping"})
    ws.feed({"type": "shake", "toyId": "t1"})
    gen = sock.events()
    await asyncio.wait_for(anext(gen), 1)
    assert "Pong" in ws.sent
    await gen.aclose()


async def test_socket_sends_client_pings():
    ws = FakeSocket()
    connect, _ = _factory([ws])
    sock = LovenseEventSocket(
        LovenseConfig(), connect=connect, ping_interval=0.01
    )
    gen = sock.events()
    pump = asyncio.create_task(anext(gen))  # recv blocks; ping task runs
    await _wait_for(
        lambda: any(
            isinstance(s, str) and json.loads(s) == {"type": "ping"}
            for s in ws.sent
            if s != "Pong"
        ),
        timeout=0.5,
    )
    pump.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pump
    await gen.aclose()


async def test_socket_reconnects_on_event_closed():
    ws1, ws2 = FakeSocket(), FakeSocket()
    connect, calls = _factory([ws1, ws2])
    delays = []

    async def fake_sleep(s):
        delays.append(s)

    sock = LovenseEventSocket(
        LovenseConfig(), connect=connect, backoff_max=0.05, sleep=fake_sleep
    )
    ws1.feed({"type": "event-closed"})
    ws2.feed({"type": "shake", "toyId": "t1"})
    gen = sock.events()
    assert (await asyncio.wait_for(anext(gen), 1))["type"] == "shake"
    assert len(calls) == 2
    await gen.aclose()


async def test_socket_backoff_is_capped():
    sockets = [FakeSocket() for _ in range(5)]
    connect, calls = _factory(sockets)
    delays = []

    async def fake_sleep(s):
        delays.append(s)

    sock = LovenseEventSocket(
        LovenseConfig(), connect=connect, backoff_max=0.05, sleep=fake_sleep
    )
    for ws in sockets[:-1]:
        ws.drop()
    sockets[-1].feed({"type": "shake", "toyId": "t1"})
    gen = sock.events()
    assert (await asyncio.wait_for(anext(gen), 1))["type"] == "shake"
    assert len(calls) == 5
    assert delays and max(delays) <= 0.05
    await gen.aclose()


async def test_socket_skips_malformed_frames():
    ws = FakeSocket()
    connect, _ = _factory([ws])
    sock = LovenseEventSocket(LovenseConfig(), connect=connect)
    ws.feed("not json")
    ws.feed({"type": "shake", "toyId": "t1"})
    gen = sock.events()
    assert (await asyncio.wait_for(anext(gen), 1))["type"] == "shake"
    await gen.aclose()


# --- Task 5: parse_event + ToyEventSource ---------------------------------

from lovecash.triggers.events import ToyStatus
from lovecash.triggers.toy_events import ToyEventSource, parse_event


def test_parse_each_lovense_frame():
    (shake,) = parse_event({"type": "shake", "toyId": "t1"})
    assert shake == ToyEventTrigger(event=ToyEventKind.SHAKE, toy_id="t1")

    (press,) = parse_event(
        {"type": "button-pressed", "toyId": "t1", "data": {"index": 0}}
    )
    assert press.event is ToyEventKind.BUTTON_PRESSED
    assert press.button_index == 0

    (depth,) = parse_event(
        {"type": "depth-changed", "toyId": "t1", "data": {"value": 12}}
    )
    assert depth.event is ToyEventKind.DEPTH_CHANGED
    assert depth.value == 12

    (batt,) = parse_event(
        {"type": "battery-changed", "toyId": "t1", "data": {"value": 84}}
    )
    assert batt == ToyStatus(toy_id="t1", battery=84)

    (status,) = parse_event(
        {"type": "toy-status", "toyId": "t1", "data": {"connected": False}}
    )
    assert status == ToyStatus(toy_id="t1", connected=False)

    listed = parse_event(
        {
            "type": "toy-list",
            "toyList": [
                {
                    "id": "t1",
                    "name": "Max 2",
                    "type": "max",
                    "hVersion": "2",
                    "fVersion": 300,
                    "nickname": "toy-nickname",
                    "battery": 100,
                    "connected": True,
                }
            ],
        }
    )
    assert listed == [
        ToyStatus(toy_id="t1", name="Max 2", battery=100, connected=True)
    ]


def test_parse_motion_uses_max_speed():
    (motion,) = parse_event(
        {
            "type": "motion-changed",
            "toyId": "t1",
            "data": {
                "motionData": [
                    {"direction": 1, "speed": s, "position": 50}
                    for s in (10, 40, 25, 30, 15)
                ]
            },
        }
    )
    assert motion.event is ToyEventKind.MOTION_CHANGED
    assert motion.value == 40


def test_parse_motion_empty_burst():
    assert (
        parse_event(
            {"type": "motion-changed", "toyId": "t1", "data": {"motionData": []}}
        )
        == []
    )


def test_parse_ignores_non_ruleable():
    assert parse_event({"type": "button-down", "toyId": "t1", "data": {"index": 0}}) == []
    assert (
        parse_event(
            {
                "type": "function-strength-changed",
                "toyId": "t1",
                "data": {"function": "vibration", "value": 20, "index": 0},
            }
        )
        == []
    )
    assert parse_event({"type": "wat"}) == []


async def test_source_routes_triggers_and_status():
    ws = FakeSocket()
    connect, _ = _factory([ws])
    triggers, statuses = [], []

    async def emit(ev):
        triggers.append(ev)

    async def on_status(st):
        statuses.append(st)

    source = ToyEventSource(
        LovenseConfig(), on_toy_status=on_status, connect=connect
    )
    assert source.source_id == "toy-events"
    ws.feed({"type": "shake", "toyId": "t1"})
    ws.feed({"type": "battery-changed", "toyId": "t1", "data": {"value": 84}})
    runner = asyncio.create_task(source.run(emit))
    await _wait_for(lambda: len(triggers) == 1 and len(statuses) == 1)
    await source.close()
    runner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await runner

    assert triggers[0].event is ToyEventKind.SHAKE
    assert statuses[0] == ToyStatus(toy_id="t1", battery=84)
    assert all(isinstance(t, ToyEventTrigger) for t in triggers)


# --- Task 6: orchestrator wiring ------------------------------------------

from lovecash.config import BchConfig, Settings
from lovecash.core.orchestrator import Orchestrator
from lovecash.core.router import ToyRouter
from lovecash.models import EventRule
from lovecash.safety import SafetyState
from lovecash.triggers.events import ToyTarget

# Same dummy xpub as tests/conftest.py (duplicated: tests/ is not a package).
XPUB = "xpub6DF5GApwf8FAAoTTwY6Gk2ZXC1uM6kCqqZBBTEC2Bc6ELxQn6ftHxexXxr8RsQpka7racgE7QbVs4JBdCXn7XL63LEF8tAC6u6KrT5eeseS"

_DEPTH_RULE = EventRule(
    name="deep",
    event=ToyEventKind.DEPTH_CHANGED,
    duration_s=3,
    min_value=5,
    max_value=10,
    toy="t2",
)


def _orch(events_enabled=False, event_rules=()):
    settings = Settings(
        lovense=LovenseConfig(events_enabled=events_enabled),
        bch=BchConfig(xpub=XPUB),
        event_rules=list(event_rules),
    )
    safety = SafetyState(0)
    router = ToyRouter(safety, settings.limits)
    return Orchestrator(settings, router=router)


def test_orchestrator_adds_source_only_when_enabled():
    on = _orch(events_enabled=True)
    assert "toy-events" in [s.source_id for s in on.sources]
    off = _orch(events_enabled=False)
    assert "toy-events" not in [s.source_id for s in off.sources]


async def test_handle_event_dispatches_event_rule_command():
    orch = _orch(event_rules=[_DEPTH_RULE])
    calls = []
    orig = orch.router.dispatch

    async def spy(cmd, target, tip_id=None):
        calls.append((cmd, target, tip_id))
        await orig(cmd, target, tip_id=tip_id)

    orch.router.dispatch = spy
    await orch._handle_event(
        ToyEventTrigger(event=ToyEventKind.DEPTH_CHANGED, toy_id="src", value=7)
    )
    assert len(calls) == 1
    cmd, target, tip_id = calls[0]
    assert target.toy_ids == ["t2"]
    assert tip_id is None  # no payment status tracking for event commands


async def test_event_rule_target_none_fans_out():
    rule = _DEPTH_RULE.model_copy(update={"toy": None})
    orch = _orch(event_rules=[rule])
    calls = []
    orig = orch.router.dispatch

    async def spy(cmd, target, tip_id=None):
        calls.append(target)
        await orig(cmd, target, tip_id=tip_id)

    orch.router.dispatch = spy
    await orch._handle_event(
        ToyEventTrigger(event=ToyEventKind.DEPTH_CHANGED, toy_id="src", value=7)
    )
    assert calls == [ToyTarget(toy_ids=[])]  # empty = all toys


async def test_toys_status_merges_fieldwise():
    orch = _orch()
    seen = []

    async def obs(d):
        seen.append(dict(d))

    orch.add_toy_status_observer(obs)
    await orch._on_toy_status(ToyStatus(toy_id="t1", battery=84))
    await orch._on_toy_status(ToyStatus(toy_id="t1", connected=False))
    merged = orch.toys_status["t1"]
    assert merged.battery == 84  # kept from first update
    assert merged.connected is False
    assert len(seen) == 2
    assert seen[-1]["t1"] is merged


async def test_payment_path_unchanged(orch_and_ctrl):
    orch, ctrl = orch_and_ctrl
    tip = PaymentTrigger(
        source_id="bch", txid="deadbeef", amount_sats=5000, confirmations=1
    )
    await orch._handle_event(tip)
    assert len(ctrl.commands) == 1
    assert ctrl.commands[0].strength == 4  # tease rule from conftest
