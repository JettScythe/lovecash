# 2026-09-11 — PR #11 review follow-ups

- Date: 2026-09-11
- Base branch: main (PR #11 head)
- Working branch: agent/goal-show-covenant
- Model: Kimi K3

## Goal

Fold the self-review findings into the branch: pledge-floor consistency,
dead config removal, env-override priority, cache bound, docs cons.

## Files Changed

- `contracts/web/pledge_tx.mjs` + `pledge_ui.js` — client pledge floor
  546 → 5000, matching the covenant. Previously a 546–4999 pledge passed
  all client checks, the wallet signed and broadcast it, and the node
  rejected it.
- `contracts/web/pledge_tx.test.mjs` — floor test now pins 4999/5000.
- `lovecash/config.py` — removed dead `wc_chain`/`resolved_wc_chain`
  (WizardConnect transport derives the network from the pot address);
  `from_yaml` now drops file keys that LOVECASH_* env vars set, so env
  beats YAML as docs/self-hosting.md promises (pydantic-settings gives
  init data priority over env by default).
- `lovecash/server/app.py` — dropped `wc_chain` from /api/goal_pot;
  `_meta_cache` bounded at 512 entries (FIFO) — keys are attacker-chosen.
- `docs/covenant-goal-shows.md` — status corrected (shipped,
  chipnet-verified), transport decision updated (WizardConnect shipped),
  new "Limitations (v1 accepted cons)" section incl. the min-pledge math.
- `docs/self-hosting.md` — rate-limit note for the Electrum-proxy
  endpoints (raw-tx fallback amplification).
- `tests/test_config_template.py` — env-beats-yaml regression test.
- `lovecash/server/ui/static/pledge.bundle.js` — rebuilt.

## Min-pledge math (why 5000 stays)

Refund tx ≈ 722–756 bytes (measured from the real redeem script: 404 B)
→ ~750 sats at 1 sat/byte. Payout = amount + 800 (receipt dust) − fee
must clear the 546-sat dust limit: floor = 496 sats at realistic fees,
746 sats under the covenant's 1000-sat fee cap. 5000 = 6.7× worst-case
margin (~1.1¢ at $227/BCH). The pledge's fixed overhead (~800 dust +
~820 fee) dominates griefing cost at any minimum, so lowering the floor
buys nothing. Hardcoded in the covenant — changing it means recompile +
redeploy + golden regen.

## Commands Run

- `uv run pytest -q` — 167 passed (1 new)
- `uv run mypy`, `uv run ruff check lovecash tests` — clean
- `docker … npm test` — 38 JS tests pass; bundle rebuilt
- Live: `LOVECASH_SERVER__BIND_PORT=8083 uv run lovecash serve -c …`
  failed before the fix (bound 8080), binds 8083 after.

## Outcome

Tests: pass (167 py + 38 js)
Lint: pass
Build: pass (bundle rebuilt)

## Notes

- Covenant-show creation is intentionally absent from the dashboard
  (pair-to-deploy deferred — the relay is watch-only and cannot sign the
  genesis tx). The dashboard card shows status + docs pointer only.
- Docs cons added; remaining review follow-ups open: bundle-staleness CI
  check.
