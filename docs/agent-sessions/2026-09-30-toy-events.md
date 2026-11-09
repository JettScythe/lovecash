# Session: toy events pipeline (issue #20 piece 1)

- Date: 2026-09-30
- Base branch: main
- Working branch: agent/toy-events
- Model(s): Kimi K3 only (user constraint; main agent + final reviewer)

## Goal

Implement issue #20 piece 1: Lovense Toy Events API (game-mode /v1
WebSocket) as an event source — shake/button-pressed/depth-changed/
motion-changed fire new edge-triggered `EventRule`s; battery/status feed
the dashboard. Commands stay on the local HTTP transport (the events
socket is receive-only; the command-capable socket API is a cloud
service, rejected for lovecash).

Spec: `docs/superpowers/specs/2026-09-30-toy-events-design.md`
Plan: `docs/superpowers/plans/2026-09-30-toy-events.md`

## Files Changed

```
 config.example.yaml                                |  19 +
 docs/developing.md                                 |   3 +-
 docs/superpowers/plans/2026-09-30-toy-events.md    | 211 ++++++++
 docs/superpowers/specs/2026-09-30-toy-events-design.md | 215 ++++++++
 lovecash/config.py                                 |  12 +-
 lovecash/config.template.yaml                      |  26 +
 lovecash/core/orchestrator.py                      |  63 ++-
 lovecash/engine/rules.py                           |  53 +-
 lovecash/lovense/eventsocket.py                    | 137 +++++
 lovecash/models.py                                 |  63 +++
 lovecash/server/app.py                             |  28 +-
 lovecash/server/ui/dashboard.py                    |   5 +-
 lovecash/triggers/events.py                        |  26 +-
 lovecash/triggers/toy_events.py                    |  99 ++++
 pyproject.toml                                     |   4 +-
 tests/test_server.py                               |  51 ++
 tests/test_toy_events.py                           | 558 +++++++++++++++++++++
 tests/test_toy_events_live.py                      |  25 +
 uv.lock                                            |   2 +
```

## Commands Run

- Per-task TDD: `uv run --extra server pytest tests/test_toy_events.py -v`
  (RED watched per task, then GREEN), `tests/test_server.py -v`
- Full suite: `uv run --extra server pytest -v`
- CI order: `uv run python -m compileall lovecash tests`,
  `uv run ruff check .`, `uv run mypy`
- Integration: `uv run pytest -m integration tests/test_toy_events_live.py -v`

## Outcome

`Tests: pass (252; 27 new in test_toy_events.py + 1 in test_server.py)`
`Lint: pass`
`Build: pass (compileall; mypy clean, 69 files)`

## Notes

- New core dep: `websockets` (event socket client; headless mode needs it).
- Live integration test currently FAILS against the user's Lovense
  Connect desktop: wss handshake succeeded after matching the
  controller's verify-off posture (the app's local cert had expired),
  but the server closes /v1 with 1000 — Lovense docs put the Toy Events
  API in Lovense Remote (phone) game mode. Desktop game mode may serve
  it on a different port (docs example: 20010). `lovense.events_url`
  override exists for exactly this. Live smoke pending user input on
  which app/game-mode they can enable.
- The user's Edge 2 / Gush 2 emit no sensor events per Lovense's table;
  shake/button/depth/motion rules are proven against a fake socket only.
- Rulings (from .superpowers/sdd ledger):
  - ToyEventKind lives in models.py (spec sketched triggers/events.py;
    that direction is a circular import).
  - LovenseEventSocket takes a `sleep` injection for backoff tests.
  - events_url config override added after live-test evidence (above).
- Pre-commit ruff pass shuffled nothing unexpected; ASYNC110 added to
  tests per-file ignores (poll-a-predicate is the standard test idiom).

## Follow-ups

- Live smoke with game mode enabled (user action), then close the
  events_url question (same endpoint vs override needed).
- Issue #20 piece 2 (SyncTime / aligned playback) — untouched.
- Dashboard settings editor does not yet edit event_rules (config-file
  only); add when a performer asks.
