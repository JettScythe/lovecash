# Onboarding + trust UX

- Date: 2026-09-10
- Base branch: agent/dead-code-cleanup
- Working branch: agent/onboarding-trust-ux
- Model: k3

## Goal

Massively improve (1) performer onboarding and (2) tipper-facing trust
proof, with visual representation of the technical detail.

## Files Changed

- `lovecash/onboard.py` (new): shared wizard logic — detect_toys,
  toy_defaults, build_rules, render_config (used by CLI + web wizard)
- `lovecash/server/setup.py` (new): setup-mode FastAPI app, loopback-only
- `lovecash/server/ui/setup.py` (new): zero-build wizard page
- `lovecash/server/ui/tip.py`: lifecycle stepper, txid/explorer link,
  trust explainer panel
- `lovecash/cli.py`: init slimmed to shared helpers; serve falls into
  setup mode when config missing/invalid
- `docs/performers.md`: browser wizard path documented
- `tests/test_setup.py` (new), `tests/test_server.py` (markup asserts)

## Commands Run

- `pytest tests/ -q` — 111 passed
- `ruff check lovecash/ tests/` — clean
- `ruff format` — clean
- `mypy` — no issues (58 files)
- TestClient smoke: /setup renders, check-xpub derives addresses

## Outcome

Tests: pass (111)
Lint: pass
Type check: pass

## Notes

- Found + fixed pre-existing bug: multi-toy `toys:` yaml block rendered
  unindented by the CLI template path (never exercised before). Fixed in
  `onboard.render_config` with +2 continuation indent.
- Setup write refuses overwrite (409), enforces loopback via
  Sec-Fetch-Site + Host checks mirroring the relay's auth guard.
- tip_status ws messages were already broadcast but dropped by the tip
  page; stepper consumes them. Amount-match heuristic (pre-existing for
  the thanks card) now also claims the status stream — same documented
  caveat.
- "verifying" step detail comes from verify.py's tip_status extra
  (window_seconds).
- Not committed yet — awaiting user request for commit/PR.

## Addendum: live settings editor (same branch)

User rejected edit-yaml + restart loop. Added:

- `POST/GET /api/settings` (auth-guarded like panic/resume): hot-applies
  limits (mutated in place; controllers refreshed via
  `router.refresh_limits()` + `LovenseController.set_limits`), rules
  (engine swap via `orchestrator.set_rules`), alerts (mutated in place;
  overlay re-renders per request). Persists via new
  `Settings.save_yaml` (chmod 600).
- `create_app(settings, config_path)` — cli serve passes the path.
- Dashboard settings card: sliders for strength/duration, playback +
  trim selects, alert min/goal/accent/sound, rules as validated JSON
  (zero-build: no YAML parser client-side; merges over fetched object
  so untouched fields aren't reset to defaults).
- Restart-level (unchanged): xpub, electrum servers, toy wiring.
- Tests: roundtrip hot-apply+persist, invalid rules 422, cross-site 403.

Verify: 114 tests pass, ruff + mypy clean.

Note: save_yaml is a plain dump — template comments not preserved.
