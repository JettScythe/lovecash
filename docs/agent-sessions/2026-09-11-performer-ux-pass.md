# 2026-09-11 — Performer UX pass (overlay label, token lookup, goal-show card)

- Date: 2026-09-11
- Base branch: main (PR #11 head)
- Working branch: agent/goal-show-covenant
- Model: Kimi K3

## Goal

Performer feedback: token categories are incomprehensible to most
performers; there's no way to even SEE covenant show state in the
dashboard; the overlay can't distinguish a covenant pot bar from the
session tip-goal bar.

Scope judgment (user: "go with your best judgement"): build the small and
medium items, defer pair-to-deploy covenant setup (needs wallet signing —
relay is watch-only) as post-V1.

## Files Changed

- `lovecash/server/ui/overlay.py` — goal bar label: "Goal show · all or
  nothing" when tracking the covenant pot, "Tip goal" for the session goal.
- `lovecash/server/app.py` — new `GET /api/token_meta?category=` (BCMR
  metadata proxied from bcmr.paytaca.com, in-memory cache, read-only);
  `/api/status` goal_pot now includes `deadline`.
- `lovecash/server/ui/dashboard.py` — token rule rows resolve category →
  "✓ name (symbol) · N decimals" and autofill the rule name; new "Goal
  show" card (live/settled pill, pot/goal, deadline, address; docs pointer
  when unconfigured).
- `docs/self-hosting.md` — /api/token_meta added to the endpoint table.

## Commands Run

- `uv run pytest -q` — 166 passed
- `uv run mypy`, `uv run ruff check lovecash tests` — clean
- `uv run lovecash serve -c /tmp/config.shows-8081.yaml` + curl — dashboard
  200, token_meta validation (422 on short hex) and miss path
  (`{"ok":false}`) verified; inline JS `node --check` OK

## Outcome

Tests: pass (166)
Lint: pass
Build: not applicable (no bundle changes this pass)

## Notes

- token_meta HIT path (ok:true) not verified against a live registry entry
  — the response parse is defensive; worst case the UI shows "no metadata
  found". Paytaca's list endpoint 404s, so no easy discovery of a known
  category.
- Env-var overrides (LOVECASH_SERVER__BIND_PORT) do NOT apply when a config
  path is passed — `from_yaml` uses `model_validate`, which skips env
  parsing. docs/self-hosting.md overstates this; worth fixing separately.
- A bare `lovecash serve` (PID 46206, default config.yaml) was already
  running on 8080 — left untouched; smoke tests ran on 8081.
- Dashboard editor and goal-show card still not click-tested in a browser.
