# Session: hardening and cleanup

- Date: 2026-09-09
- Base branch: main (phase 1-2) / agent/hardening-and-cleanup (phase 3)
- Working branch: agent/hardening-and-cleanup (PR #5), then
  agent/ui-ux-overhaul (stacked on PR #5, not yet pushed)
- Model(s): kimi-for-coding/k3 (+2 specialist subagents for the
  dashboard and tip-page HTML)

## Goal

Remove a hardcoded node RPC credential, then work through a prioritized
codebase review: security first, then correctness, then broken docs/repo
hygiene, then small hardening.

## Files Changed

`git diff --stat main...HEAD`: 26 files changed, 647 insertions(+),
100 deletions(-). See `git log main..HEAD` for the 11 commits.

## Commands Run

- `uv run --extra server pytest -q` (repeatedly; final: 94 passed)
- `uv run ruff check .` (final: clean)
- `uv run mypy` (final: no issues in 53 files)
- `uv run python -m compileall lovecash tests tools`
- Live TLS verification probe of all three default Electrum servers
  (all pass with certificate verification on)

## Outcome

- Tests: pass (94, up from 80)
- Lint: pass
- Build (compileall): pass
- Type check: pass (now enforced in CI)

## What changed (by theme)

Security:

1. tools/harvest_dsproof_push.py no longer carries real node RPC
   credentials (env-only). Confirmed via `git grep` over all history
   that the password never entered a commit — no history rewrite needed.
   The password should still be rotated: it sat in a plaintext file.
2. /panic and /resume now refuse Sec-Fetch-Site: cross-site requests and
   non-loopback Host headers when no relay token is set — a drive-by
   webpage could previously clear a panic stop via a plain form POST.
3. Electrum connections verify TLS certificates by default
   (`tls_verify: true` per server; all three default servers pass).
4. Tips waiting on a confirmation (high-value or DSProof-refused) keep
   their address subscribed across window rotation and reconnects, and
   are credited when the block lands. Previously they could silently
   vanish.

Correctness: Decimal money math in _sum_to_us; "confirming" announced
once per tip; a refused tx is not re-verified on every scan; only the
notified scripthash is scanned per notification; seen-set bounded
(200k FIFO); override mode no longer claims "active" for dropped
commands; doctor's truncated Lovense message completed.

Features/docs: added `lovecash run` (headless; docs already promised
it); renamed docs/toubleshooting.md (4 broken links); tools/*.py use
server_pool(); Game Mode references removed from CLI (per b40ebff);
config.example.yaml re-synced and now validated by a test.

Hygiene: .DS_Store untracked; .coverage/config.yaml.bak/scratch_*
ignored; mypy in CI; ruff targets py314; stale type: ignore comments
removed; commitizen stale version field dropped.

## Notes

- Phase 3 (ui-ux-overhaul branch): AlertConfig + SessionStats backend,
  /api/status + /api/toys, and three zero-build pages — rewritten
  /overlay (tiered chime/confetti alerts, goal bar, USD, memo),
  /dashboard (performer control panel with panic/resume), /tip (viewer
  tipping page with memo + landed-confirmation heuristic). Dashboard and
  tip page HTML drafted by specialist subagents against a precise API
  spec, then reviewed in-tree (textContent-only rendering of on-chain
  memo text verified by reading both files).
- Browser behavior of the new pages was NOT runtime-tested (no live
  relay run); warrant one manual pass: open /dashboard, /tip on a phone,
  and the overlay in OBS while firing test tips.
- Assumption: all three default Electrum servers will keep valid certs;
  tls_verify can be set false per server for self-signed hosts.
- Offline-tip gap FIXED (second half of the session): persisted watcher
  state (`lovecash/bch/state.py`, `~/.lovecash/state-<xpub-tail>.json`,
  `LOVECASH_STATE_DIR` override) with atomic writes; restarts replay
  only unseen txs through the normal tiers. Fail-safe: missing/corrupt/
  foreign state seeds from current history WITHOUT emitting (miss
  rather than double-fire). Also fixed the sibling gap: rotated-out
  addresses were unsubscribed on reconnect; all watched addresses are
  now re-subscribed.
- Commit 3030b49 accidentally swept in the .DS_Store untracking; noted
  here rather than rewritten.
- scratch_rules.py / scratch_tip.py left on disk (untracked, now
  ignored) — they reference removed APIs (orch.engine, _handle_tip) and
  can be deleted by hand.
- Not pushed; branch is local pending review.
