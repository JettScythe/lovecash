# 2026-09-11 — Goal-show UI gating + dashboard rules editor

- Date: 2026-09-11
- Base branch: main (PR #11 head)
- Working branch: agent/goal-show-covenant
- Model: Kimi K3

## Goal

User feedback after the chipnet covenant tests: (1) covenant goal shows
are occasional — the UI must not be visible when there's no live show;
(2) the dashboard rules editor was a raw JSON textarea — "horrible UX".

## Files Changed

- `lovecash/triggers/payment.py` — pot balance callback now carries an
  `active` flag (pot UTXO exists); `_maybe_auto_claim` accepts a prefetched
  pot. Transient listunspent failures assume active rather than hide the UI.
- `lovecash/core/orchestrator.py` — observer signature `(balance, active)`,
  new `pot_active` state.
- `lovecash/server/app.py` — `goal_pot` in `/api/status` and the ws
  broadcast include `active`.
- `lovecash/server/ui/tip.py` — goal-show card hidden when unconfigured
  (was already) or settled (new).
- `lovecash/server/ui/overlay.py` — OBS goal bar disappears when the show
  settles (pot claimed) instead of sticking at 0%.
- `contracts/web/pledge_ui.js` (+ rebuilt
  `lovecash/server/ui/static/pledge.bundle.js`) — configured-but-settled
  show renders "This goal show is over — the pot was claimed." instead of
  the pledge form.
- `lovecash/server/ui/dashboard.py` — JSON textareas replaced with
  structured row editors for tip rules and token rules (all model fields:
  name, ranges, action, strength, duration, toy, require_conf; add/delete
  rows; client-side validation, server-side pydantic still the backstop).
  "No cap" max is 2^53-1 (largest exactly-representable JS int) instead of
  the server's 2^63-1, which round-trips through JS as 2^63.
- `docs/self-hosting.md` — endpoint table gained /tip, /dashboard,
  /api/*; noted HTTPS is required for wallet pairing, tunnels as the
  no-domain option.
- `tests/test_token_tips.py` — pot callbacks updated to the new signature.

## Commands Run

- `uv run pytest -q` — 166 passed
- `uv run mypy` — clean
- `uv run ruff check lovecash tests` — clean
- `docker run node:22-alpine npx esbuild …` — pledge bundle rebuilt
- `uv run lovecash serve -c config.chipnet-shows.yaml` + curl — /tip,
  /overlay, /dashboard 200; /api/status reports `active: false` for the
  settled chipnet show; /api/goal_pot reports `utxo: null`
- extracted inline scripts, `node --check` — parse OK

## Outcome

Tests: pass (166)
Lint: pass
Build: pass (bundle rebuilt)

## Notes

- Dashboard rule editor NOT click-tested in a real browser (no jsdom);
  verified by code review + JS parse + endpoint smoke test. Worth one
  manual save-cycle before shipping.
- Settled semantics: pot UTXO gone ⟺ claimed (refunds always continue the
  pot), so "inactive" is unambiguous. A configured-but-never-seeded show
  also reads inactive — same correct UI (nothing to pledge to).
- /dashboard HTML is served unauthenticated (controls are token/loopback
  guarded); documented as such.
- Viewer hosting question answered in docs/self-hosting.md: reverse proxy
  or tunnel to `https://host/tip`.
