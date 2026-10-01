# Toy Events Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Lovense toy events (shake, button-pressed, depth, motion) fire performer-authored rules, and surface battery/status in the dashboard — issue #20 piece 1.

**Architecture:** A reconnecting `LovenseEventSocket` client (local `/v1` WebSocket, game mode) feeds a `ToyEventSource` implementing the existing `TriggerSource` protocol. Rule-able events become `ToyEventTrigger`s matched by new edge-triggered `EventRule`s in `RulesEngine.resolve_event`; status events update `Orchestrator.toys_status`, merged into the existing `/api/toys` poll. Commands stay on the existing HTTP controller path — clamp and panic gate untouched.

**Tech Stack:** Python 3.14, pydantic v2, `websockets` (new core dep), pytest/pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-09-30-toy-events-design.md`

## Global Constraints

- Safety invariants (spec §8): limits clamp and panic gate live in `LovenseController` below all dispatch paths; nothing in the event path calls `SafetyState.resume()`; status events never reach the rules engine.
- `websockets` goes in `[project.dependencies]` (headless `lovecash run` needs it), added via `uv add` so `uv.lock` stays in sync.
- `ToyEventKind` lives in `lovecash/models.py`, NOT `triggers/events.py` as the spec's sketch shows — `triggers/events.py` imports from `models.py`, so the reverse would be circular.
- Edge state is keyed `(rule_index, toy_id)` — value streams are per-toy. Engine rebuild (Orchestrator.set_rules) resets it; no explicit reset API.
- Verification in CI order: `uv run python -m compileall lovecash tests` → `uv run ruff check .` → `uv run mypy` → `uv run --extra server pytest -v`.
- Conventional Commits (commitizen-enforced at pre-commit).

## Review Focus

1. Keepalive is bidirectional in Lovense's docs: client sends `{"type":"ping"}` every 5 s AND must answer an inbound `{"type":"ping"}` with raw `Pong`. Missing either drops the connection mid-show → tests in Task 4.
2. `event-closed` (game mode toggled off) must reconnect with capped backoff, not a hot spin → backoff-sequence test in Task 4.
3. `motion-changed` with an empty `motionData` list — `max()` on empty would crash the consumer → guard test in Task 5.
4. depth/motion frame missing `data.value` → no crash, no fire, edge state updated to out-of-band → tests in Tasks 3 and 5.
5. Event rule with `toy=None` (target = all toys) under the multi-toy router must fan out to every toy → dispatch test in Task 6.

---

### Task 1: `websockets` dep + event models

**Files:**
- Modify: `pyproject.toml` (via `uv add websockets`), `uv.lock`
- Modify: `lovecash/models.py` (append `ToyEventKind`)
- Modify: `lovecash/triggers/events.py`
- Test: `tests/test_toy_events.py` (new; all later tasks add here too)

**Interfaces:**
- Produces:
  - `lovecash.models.ToyEventKind(StrEnum)`: `SHAKE="shake"`, `BUTTON_PRESSED="button-pressed"`, `DEPTH_CHANGED="depth-changed"`, `MOTION_CHANGED="motion-changed"`
  - `lovecash.triggers.events.ToyEventTrigger(BaseModel)`: `kind: Literal["toy_event"]="toy_event"`, `event: ToyEventKind`, `toy_id: str`, `value: float | None = None`, `button_index: int | None = None`
  - `lovecash.triggers.events.ToyStatus(BaseModel)`: `toy_id: str`, `name: str | None = None`, `battery: int | None = None`, `connected: bool | None = None` (None = "no info", merged field-wise by the orchestrator)
  - `TriggerEvent = PaymentTrigger | ToyEventTrigger`

- [ ] **Step 1: Failing test** — `tests/test_toy_events.py::test_trigger_union_discriminates`: `ToyEventTrigger(event=ToyEventKind.SHAKE, toy_id="abc")` has `kind=="toy_event"` and defaults `value`/`button_index` None; a `PaymentTrigger` and a `ToyEventTrigger` both validate as `TriggerEvent` via `TypeAdapter` and keep their own `kind`.
- [ ] **Step 2: Run** — `uv run --extra server pytest tests/test_toy_events.py -v` → ImportError on `ToyEventTrigger`.
- [ ] **Step 3: Implement** — `uv add websockets`; add `ToyEventKind` to `models.py` (next to `Action`); add the two models + union to `triggers/events.py`.
- [ ] **Step 4: Run** — same command → PASS.
- [ ] **Step 5: Commit** — `feat: toy event trigger and status models`

### Task 2: `EventRule` model + settings field

**Files:**
- Modify: `lovecash/models.py` (append `EventRule`)
- Modify: `lovecash/config.py` (`Settings.event_rules: list[EventRule] = []`, next to `token_rules`)
- Test: `tests/test_toy_events.py`

**Interfaces:**
- Consumes: `ToyEventKind` (Task 1), `CommandFields`/`TipRule` pattern (`models.py`).
- Produces: `EventRule(CommandFields)` with `name: str`, `event: ToyEventKind`, `min_value: float = 0`, `max_value: float = 2**63 - 1`, `button_index: int | None = None`, `source_toy: str | None = None`, `toy: str | None = None`; `matches(event: ToyEventTrigger) -> bool`; `to_command() -> ToyCommand`.

- [ ] **Step 1: Failing tests** —
  - `test_event_rule_rejects_narrowed_band_on_shake`: `EventRule(name="x", event=SHAKE, duration_s=1, min_value=5)` → ValidationError ("band" in message).
  - `test_event_rule_rejects_button_index_on_depth`: `event=DEPTH_CHANGED, button_index=1` → ValidationError.
  - `test_event_rule_rejects_inverted_band`: `event=DEPTH_CHANGED, min_value=10, max_value=5` → ValidationError.
  - `test_event_rule_matches_and_to_command`: depth rule band 5-10, `source_toy="aaa"`, `toy="bbb"`; matches value 7 from "aaa", rejects value 12, rejects `toy_id="other"`; `to_command()` returns `ToyCommand` carrying the action/strength/duration fields.
- [ ] **Step 2: Run** → fails (no `EventRule`).
- [ ] **Step 3: Implement** — `EventRule` mirroring `TipRule` structure; `matches` checks `event`, `source_toy`, `button_index` (when set), and band (`value is not None and min_value <= value <= max_value`); validators per spec §3 (band narrowed from default only allowed on DEPTH_CHANGED/MOTION_CHANGED; `button_index` only on BUTTON_PRESSED; `min_value <= max_value`). Add `Settings.event_rules`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `feat: event rule model for toy-event triggers`

### Task 3: `RulesEngine.resolve_event` with edge triggering

**Files:**
- Modify: `lovecash/engine/rules.py`
- Test: `tests/test_toy_events.py`

**Interfaces:**
- Consumes: `EventRule` (Task 2), `ToyEventTrigger`/`ToyEventKind` (Task 1).
- Produces: `RulesEngine(rules, token_rules=None, event_rules: list[EventRule] | None = None)` (new third param, existing callers unaffected); `resolve_event(event: ToyEventTrigger) -> list[tuple[ToyCommand, str | None]]`.

- [ ] **Step 1: Failing tests** — build an engine with: depth rule "tease" band 1-10 target None, depth rule "intense" band 11-20 target None, shake rule target "t2", button rule `button_index=1`.
  - `test_resolve_event_fires_on_band_entry_only`: depth 5 → tease fires; depth 7 → nothing; depth 15 → intense fires; depth 3 → tease fires again (re-entry after leaving).
  - `test_resolve_event_tier_and_target`: depth 15 → only "intense" (highest min_value), target None.
  - `test_resolve_event_shake_fires_every_time`: two shakes → fires both, target "t2".
  - `test_resolve_event_button_index_filter`: press index 0 → nothing; index 1 → fires.
  - `test_resolve_event_missing_value_no_crash`: depth event `value=None` → no fire, no exception, and a subsequent in-band value fires (edge was reset to out-of-band).
- [ ] **Step 2: Run** → fails (`resolve_event` missing).
- [ ] **Step 3: Implement** — constructor stores `self._event_rules` sorted by `min_value` desc and `self._event_edge: dict[tuple[int, str], bool] = {}`. `resolve_event`: per rule — kind match, `source_toy` filter, `button_index` filter; SHAKE/BUTTON_PRESSED fire per event; DEPTH/MOTION compute `in_band`, fire `in_band and not prev`, store `self._event_edge[(i, event.toy_id)] = in_band`; collect best per `r.toy` (highest `min_value`); return `[(r.to_command(), r.toy) ...]`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `feat: edge-triggered event rule matching in rules engine`

### Task 4: `LovenseEventSocket` client

**Files:**
- Create: `lovecash/lovense/eventsocket.py`
- Test: `tests/test_toy_events.py`

**Interfaces:**
- Consumes: `LovenseConfig`; `websockets` (Task 1).
- Produces:
  - `LovenseEventSocket(cfg: LovenseConfig, app_name: str = "lovecash", connect: Callable | None = None, ping_interval: float = 5.0, backoff_max: float = 30.0)` — `connect` defaults to `websockets.connect`; injected in tests.
  - `LovenseEventSocket.url_for(cfg: LovenseConfig) -> str` (static): `use_https` → `wss://{host with . → -}.lovense.club:{port}/v1`; else `ws://{host}:{port}/v1`.
  - `async def events(self) -> AsyncIterator[dict]` — reconnecting generator yielding parsed JSON dicts.
  - `async def close(self) -> None` — stops the generator at the next frame.

- [ ] **Step 1: Failing tests** — `FakeSocket` (async `recv` queue, records `send` payloads, `close`); `connect` returns it as an async context manager.
  - `test_socket_url_derivation`: https cfg → `wss://127-0-0-1.lovense.club:30010/v1`; http cfg → `ws://127.0.0.1:30010/v1`.
  - `test_socket_sends_access_first`: first sent frame parses to `{"type":"access","data":{"appName":"lovecash"}}`.
  - `test_socket_answers_server_ping_with_pong`: feed `{"type":"ping"}` → a sent frame equals raw `Pong`.
  - `test_socket_sends_client_pings`: `ping_interval=0.01`, no inbound frames → within 0.1 s a sent `{"type":"ping"}` appears.
  - `test_socket_reconnects_on_event_closed`: feed `{"type":"event-closed"}` then have `connect` called a second time (count calls); second connection's events still yield.
  - `test_socket_backoff_is_capped`: record reconnect delays across repeated drops; max delay ≤ `backoff_max` (use tiny `backoff_max=0.05` and drop 4 times).
  - `test_socket_skips_malformed_frames`: feed `"not json"`, then a valid event → only the valid one yields.
- [ ] **Step 2: Run** → fails (module missing).
- [ ] **Step 3: Implement** — single `events()` generator: loop { `async with self._connect(url) as ws`: send access; spawn ping task (`asyncio` task sending `{"type":"ping"}` every `ping_interval`); `async for raw in ws`-style recv loop: parse JSON (skip on error), `ping`→send `Pong`, `pong`→ignore, else yield; cancel ping task; on drop/`event-closed` sleep backoff (start small, double to `backoff_max`) and loop }. `close()` sets a flag checked per frame. One approach note: use `asyncio.wait_for(ws.recv(), timeout=...)` or `asyncio.wait` so the ping task and `close()` stay responsive — implementer's choice, tests pin behavior not structure.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `feat: reconnecting lovense toy-events socket client`

### Task 5: `parse_event` + `ToyEventSource`

**Files:**
- Create: `lovecash/triggers/toy_events.py`
- Test: `tests/test_toy_events.py`

**Interfaces:**
- Consumes: `ToyEventTrigger`/`ToyStatus`/`ToyEventKind` (Task 1), `LovenseEventSocket` (Task 4), `TriggerSource` ABC (`triggers/base.py`: `source_id` property, `run(emit)`, `close()`).
- Produces:
  - `parse_event(msg: dict) -> list[ToyEventTrigger | ToyStatus]` — pure mapping, `[]` for ignored/malformed.
  - `ToyEventSource(cfg: LovenseConfig, on_toy_status: Callable[[ToyStatus], Awaitable[None]] | None = None, connect=None)`; `source_id == "toy-events"`.

- [ ] **Step 1: Failing tests** —
  - `test_parse_each_lovense_frame`: the exact JSON examples from the spec (shake; button-pressed index 0; depth-changed value 12; battery-changed value 84; toy-status connected false; toy-list with one Max 2 entry incl. battery 100) → correct model instances.
  - `test_parse_motion_uses_max_speed`: 5-sample burst, speeds [10, 40, 25, 30, 15] → one trigger, `value == 40`.
  - `test_parse_motion_empty_burst`: `motionData: []` → `[]`, no exception.
  - `test_parse_ignores_non_ruleable`: `button-down`, `function-strength-changed`, `{"type":"wat"}` → `[]`.
  - `test_source_routes_triggers_and_status`: drive `run(emit)` with a fake socket feeding one shake + one battery-changed → `emit` receives the `ToyEventTrigger`, `on_toy_status` receives the `ToyStatus`, and the status never reaches `emit`.
- [ ] **Step 2: Run** → fails.
- [ ] **Step 3: Implement** — `parse_event` per spec §2 mapping (motion value = max `speed`; guard empty list). `ToyEventSource.run`: `async for msg in socket.events(): for parsed in parse_event(msg):` trigger → `await emit(parsed)`; status → `await self._on_status(parsed)` if set. `close()` delegates to socket.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `feat: toy event source bridging socket frames to triggers`

### Task 6: Orchestrator wiring + config flag

**Files:**
- Modify: `lovecash/config.py` (`LovenseConfig.events_enabled: bool = False`)
- Modify: `lovecash/core/orchestrator.py`
- Test: `tests/test_toy_events.py` (+ check existing `tests/test_orchestrator.py` if present for fixture patterns)

**Interfaces:**
- Consumes: `ToyEventSource` (Task 5), `RulesEngine` new param (Task 3), `EventRule` (Task 2).
- Produces:
  - `Orchestrator.toys_status: dict[str, ToyStatus]` (field-wise merge of updates: only non-None fields overwrite).
  - `Orchestrator.add_toy_status_observer(obs: Callable[[dict[str, ToyStatus]], Awaitable[None]])` — observers get the full merged dict.
  - `Orchestrator.set_rules(rules, token_rules=None, event_rules=None)` — new optional third param.
  - `_handle_event` branches: `ToyEventTrigger` → `resolve_event` + `router.dispatch(cmd, target)` (no `tip_id`).

- [ ] **Step 1: Failing tests** —
  - `test_orchestrator_adds_source_only_when_enabled`: `Settings` with `lovense.events_enabled=True` → a source with `source_id=="toy-events"` present; `False` → absent. (Construct `Settings` minimally with a dummy xpub; check existing orchestrator tests for the established pattern first.)
  - `test_handle_event_dispatches_event_rule_command`: orchestrator with a depth `EventRule` and a recording fake router → `ToyEventTrigger` in-band dispatches the command with the rule's target; `tip_id` not required.
  - `test_event_rule_target_none_fans_out`: target-None rule → router `dispatch` called with `ToyTarget(toy_ids=[])` (all toys).
  - `test_toys_status_merges_fieldwise`: battery-changed update then toy-status disconnect for same toy → merged entry keeps battery, `connected=False`; observers called with the full dict.
  - `test_payment_path_unchanged`: existing `PaymentTrigger` flow still resolves via `resolve_all` with `tip_id=event.txid` (regression pin, likely already covered — keep or extend the closest existing test).
- [ ] **Step 2: Run** → fails.
- [ ] **Step 3: Implement** — config flag; conditional `add_source(ToyEventSource(...))`; observer list + `_broadcast_toy_status` (merge into `self.toys_status` first, then notify with the dict); `_handle_event` `isinstance` branch; `set_rules` third param passed to `RulesEngine`.
- [ ] **Step 4: Run** → PASS, plus full `uv run --extra server pytest -v` (watch for union-type fallout in existing tests).
- [ ] **Step 5: Commit** — `feat: wire toy event source into orchestrator behind events_enabled`

### Task 7: `/api/toys` merge + dashboard low-battery warning

**Files:**
- Modify: `lovecash/server/app.py:281-302` (`/api/toys`)
- Modify: `lovecash/server/ui/dashboard.py` (toys rendering, near the `/api/toys` consumer ~line 647)
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `Orchestrator.toys_status` (Task 6); existing `/api/toys` shape `{id, name, online, battery}`.
- Produces: `/api/toys` entries where event-sourced status overrides/extends GetToys data (battery, online←connected; event-only toys appended with `source: "events"`).

- [ ] **Step 1: Failing test** — `test_api_toys_merges_event_status`: seed `orchestrator.toys_status` with a battery value for a toy GetToys also reports and one event-only toy → response shows the event battery for the first and includes the second. Follow the existing `test_server.py` app-fixture pattern.
- [ ] **Step 2: Run** → fails.
- [ ] **Step 3: Implement** — merge in `api_toys`; dashboard: low-battery styling on the existing battery display when `< 20` (check whether a warning already exists — if it does, no UI change, say so in the commit body).
- [ ] **Step 4: Run** — `uv run --extra server pytest tests/test_server.py -v` → PASS.
- [ ] **Step 5: Commit** — `feat: merge event-sourced toy status into dashboard toys api`

### Task 8: Config surface, integration test, docs, live smoke

**Files:**
- Modify: `lovecash/config.template.yaml`, `config.example.yaml` (commented `events_enabled: false` under `lovense:` with "needs game mode ON in the Lovense app")
- Create: `tests/test_toy_events_live.py` (`pytestmark = pytest.mark.integration`)
- Modify: `docs/developing.md` (module table: `lovense/eventsocket.py`, `triggers/toy_events.py` one-liners)
- Create: `docs/agent-sessions/2026-09-30-toy-events.md`
- Test: `tests/test_config_template.py` (extend if it validates the template parses)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Failing test** — none for YAML comments; instead write `tests/test_toy_events_live.py` first: connect `LovenseEventSocket` to the real configured app, assert a `toy-list` (or any) frame arrives within 10 s. Marked `integration` so default runs skip it.
- [ ] **Step 2: Run** — `uv run pytest -m integration tests/test_toy_events_live.py -v` → SKIP/fail without game mode is expected locally; the test is pinned for hardware runs.
- [ ] **Step 3: Implement** — template/example comments, docs table rows, session log per AGENTS.md (date, branches, model Kimi K3, goal, diff stat, commands, outcome, notes).
- [ ] **Step 4: Full verification** — CI order: `uv run python -m compileall lovecash tests`, `uv run ruff check .`, `uv run mypy`, `uv run --extra server pytest -v`. Then live smoke with the user: enable game mode, `LOVECASH_LOVENSE__EVENTS_ENABLED=true`, watch `toy-list`/battery arrive for the Edge 2/Gush 2.
- [ ] **Step 5: Commit** — `docs: events config surface, integration test, session log`

---

## Post-implementation

- Whole-branch review via requesting-code-review (Kimi K3 reviewer, per user's model constraint).
- Session-log commit separate, per AGENTS.md.
