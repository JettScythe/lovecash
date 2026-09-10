# Dead-code cleanup

- Date: 2026-09-10
- Base branch: agent/ui-ux-overhaul
- Working branch: agent/dead-code-cleanup
- Model: k3 (main) + scout subagents for audit

## Goal

Full-tree over-engineering audit, then cut what user approved.

## Files Changed

`git diff --stat agent/ui-ux-overhaul...HEAD` → 33 files, +104/-329.

## Commands Run

- `pytest tests/ -q` (x3)
- `ruff check lovecash/ tests/ tools/`
- `ruff format lovecash/ tests/ tools/`
- `uv lock`

## Outcome

Tests: pass (102)
Lint: pass
Build: not applicable (uv lock re-resolved clean)

## Notes

- User vetoed cuts: `/qr.svg`, `/uri` endpoints and `tools/observe_dsproof.py`
  stay (possible external consumers / useful debugging tool).
- User chose to *use* `TipStatus` enum rather than delete it: moved to
  `triggers/status.py`, all status literals in player/payment/app now use it.
- ui/*.py JS duplication deliberately kept: zero-build one-file-per-page
  design; sharing would cost more than it saves.
- `usd_to_sats` lost one stale-price warning log line (property still
  guards correctly).
- Follow-ups: none.
