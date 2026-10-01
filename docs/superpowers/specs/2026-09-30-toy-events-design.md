# Toy Events Pipeline — Design Spec

- Date: 2026-09-30
- Issue: https://github.com/JettScythe/lovecash/issues/20 (piece 1 of 2)
- Branch: agent/toy-events
- Status: approved in chat 2026-09-30, implementation pre-approved

## Context

lovecash fires toy commands only from money today (BCH/CashToken tips via
`PaymentTrigger` -> `RulesEngine.resolve_all` -> `ToyRouter` -> controller).
Issue #20 asks for the Lovense Toy Events API: a local WebSocket
(`ws://{ip}:{port}/v1`, or `wss://{ip-dash}.lovense.club:30010/v1` in HTTPS
environments) served by the Lovense app in **game mode**, streaming toy
events lovecash can turn into triggers.

Two doc findings shaped this design:

1. **The local events socket is receive-only.** The command-capable
   "Standard Socket API" is a separate cloud Socket.IO service requiring a
   Lovense developer token and QR pairing — wrong product for lovecash
   (local-only, no cloud accounts). Commands stay on the existing local
   HTTP transport; the socket is purely an event source.
2. **Event-emitting toys** (per Lovense's supported table): Nora, Max 2,
   Solace, Solace Pro, Mission 2. The user's Edge 2 / Gush 2 emit none of
   the sensor events; `toy-list`/`toy-status`/`battery-changed` come from
   the app and work with any toy. Live hardware verification of
   shake/button/depth/motion rules is therefore not possible with current
   hardware — those paths are proven against a fake socket.

SyncTime / aligned PatternV2 playback (issue piece 2) is out of scope, per
the issue's own staging.

## Goals

- Performers can author rules fired by toy events: `shake`,
  `button-pressed`, `depth-changed`, `motion-changed`.
- Dashboard shows per-toy battery % and connected status, with a
  low-battery warning, fed by `toy-list` / `toy-status` / `battery-changed`.
- Safety invariants unchanged: event-fired commands travel the identical
  router -> clamp -> panic-gate path as tips; events can never clear or
  bypass the panic stop.

## Non-goals

- Command-over-WebSocket transport (cloud Socket.IO service; rejected).
- SyncTime / beat-aligned playback.
- Continuous event-value -> strength control loops (e.g. live
  depth-mapped vibration). Edge-triggered bands only; continuous mapping
  is a future feature when someone asks.
- Overlay (OBS) rendering of events. Dashboard only.

## Design

### 1. Socket client — `lovecash/lovense/eventsocket.py`

`LovenseEventSocket`: manages the `/v1` WebSocket lifecycle.

- URL derived from existing `LovenseConfig` (`host`, `port`, `use_https`);
  HTTP env -> `ws://{host}:{port}/v1`, HTTPS env ->
  `wss://{host-dash}.lovense.club:{port}/v1`. No new address config.
- Handshake: on connect send
  `{"type": "access", "data": {"appName": "lovecash"}}`; events flow after
  `access-granted`.
- Keepalive: send `{"type": "ping"}` every 5 s (server closes silent
  connections); answer any inbound `{"type": "ping"}` with `Pong`. Lovense
  docs show both directions; handle both.
- Reconnect with exponential backoff (cap ~30 s) on drop, and on
  `event-closed` (game mode disabled).
- Parses incoming JSON into typed event models; malformed frames are
  logged and skipped, never fatal.
- Implemented against a small socket wrapper so tests inject a fake — no
  real network in unit tests.
- New dependency: `websockets` (core deps — headless `lovecash run` needs
  it; the server extra already gets it transitively via uvicorn[standard]).

### 2. Event models — `lovecash/triggers/events.py`

`ToyEventTrigger` joins `PaymentTrigger` in the `TriggerEvent` union:

```python
class ToyEventKind(StrEnum):
    SHAKE = "shake"
    BUTTON_PRESSED = "button-pressed"
    DEPTH_CHANGED = "depth-changed"
    MOTION_CHANGED = "motion-changed"

class ToyEventTrigger(BaseModel):
    kind: Literal["toy_event"] = "toy_event"
    event: ToyEventKind
    toy_id: str            # source toy
    value: float | None    # depth 0-20; motion = max speed of burst 0-100
    button_index: int | None = None

TriggerEvent = PaymentTrigger | ToyEventTrigger
```

Rule-able events only. Status events (`toy-list`, `toy-status`,
`battery-changed`) never enter the trigger queue — they go to a separate
status observer path (section 5).

`motion-changed` arrives as ~5 samples per 100 ms burst; the trigger's
`value` is the max `speed` across the burst (burst intensity).

### 3. `EventRule` — `lovecash/models.py`

Mirrors `TipRule`/`TokenRule`: extends `CommandFields`, so an event rule
carries the full command surface (any action, pattern, positions, etc.),
clamped identically downstream.

```python
class EventRule(CommandFields):
    name: str
    event: ToyEventKind
    min_value: float = 0      # band; depth 0-20, motion speed 0-100
    max_value: float = 2**63 - 1
    button_index: int | None = None   # button-pressed only
    source_toy: str | None = None     # emitter; None = any toy
    toy: str | None = None            # target; None = all toys
```

Validators:

- `min_value <= max_value`.
- Value band meaningful only for `depth-changed`/`motion-changed`; shake
  and button rules must leave the default full band (a narrowed band on a
  valueless event is a dead rule that looks configured — reject it).
- `button_index` only with `button-pressed`.

### 4. Matching — `RulesEngine.resolve_event()`

Rising-edge band semantics:

- A depth/motion rule matches while `min_value <= value <= max_value`,
  but **fires only on entry** — the value must have been outside the band
  since the last fire (per-rule edge state in the engine, keyed by rule
  index in the sorted list — rule names are not unique-constrained;
  reset by `set_rules`).
- Shake/button rules fire per event (subject to `button_index` and
  `source_toy` filters).
- `source_toy` filters the emitter; `toy` selects the target, with the
  existing convention (None = all toys).
- Best match per target toy: highest `min_value` wins, mirroring the sats
  ladder — overlapping bands act as tiers (depth 1-10 "tease", 11-20
  "intense").

### 5. Wiring — orchestrator + new source

- `ToyEventSource` (`lovecash/triggers/toy_events.py`) implements the
  existing `TriggerSource` protocol (`run(emit)` / `close()`). It wraps
  `LovenseEventSocket`, emits `ToyEventTrigger`s into the shared queue,
  and forwards status events to a new `ToyStatusObserver`
  (`dict[toy_id, {name, battery, connected}]` updates).
- `Orchestrator.__init__` adds the source only when
  `settings.lovense.events_enabled` is true.
- `_handle_event` branches on event type: `PaymentTrigger` -> current
  `resolve_all` path; `ToyEventTrigger` -> `resolve_event`, dispatched
  through the same `ToyRouter` (`tip_id=None` — no payment status
  tracking for event-fired commands).
- `shutdown()` closes the event source with everything else.

### 6. Config

```yaml
lovense:
  events_enabled: false  # needs game mode ON in the Lovense app
```

Default off: without game mode enabled the source would just
reconnect-spam. Documented in `config.template.yaml` and
`config.example.yaml`. One flag, no new address surface.

### 7. Dashboard

Per-toy row (or badge on existing toy rows): battery % + connected dot,
updated live from status events via a websocket/SSE push matching the
existing dashboard update mechanism. Warning styling under 20% battery.
Headless `run` mode logs status changes instead.

### 8. Safety invariants (explicitly preserved)

- Limits clamping and the panic gate live in `LovenseController`, below
  every dispatch path — event commands pass through them identically.
- Nothing in the event path touches `SafetyState.resume()`.
- Status events can never produce commands (no route to the engine).
- Malformed/unknown event frames cannot crash the consumer loop.

## Testing

- Fake socket injected into `LovenseEventSocket`: handshake sequence,
  ping/pong both directions, reconnect on drop and on `event-closed`,
  malformed-frame tolerance.
- `EventRule` validators: band/index misuse rejected.
- `resolve_event`: edge-triggering (entry fires, repeat inside band
  doesn't, re-entry after leaving fires), tier selection, source/target
  filtering, `set_rules` resets edge state.
- `ToyEventSource`: parsed events reach the queue; status events reach
  the status observer, not the queue.
- Orchestrator branch: `ToyEventTrigger` dispatches via router with
  `tip_id=None`.
- `-m integration` live test against game mode, skipped by default (same
  pattern as the Electrum integration tests).

## Verification

CI order: `uv run python -m compileall lovecash tests`,
`uv run ruff check .`, `uv run mypy`, `uv run --extra server pytest -v`.
Live smoke test with the user's Edge 2 / Gush 2: connect, `toy-list`
battery/status visible (sensor events N/A on this hardware).

## Open follow-ups (not this branch)

- SyncTime + aligned PatternV2 playback (issue #20 piece 2).
- Continuous value->strength mapping for depth/motion.
- Event-emitting toy support notes in `KNOWN_TOYS` once hardware-verified.
