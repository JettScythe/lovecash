# Session: wallet-signed goal-show deploy (+ exact claim fee)

- Date: 2026-09-14
- Base branch: `main` (79619a5)
- Working branches: `agent/real-claim-fee`, `agent/cashscript-py-swap` (parked WIP), `agent/wallet-goal-deploy`
- Model(s): kimi-k3 (main agent, no subagents)

### Goal

Roadmap items from docs triage: (1) real claim fee instead of hardcoded
1000 sats, (2) spike cashscript-py as a JS replacement, (3) performers
create covenant goal shows with their own wallet (non-custodial claim
intact: Cashonize signs remotely via WizardConnect).

### Files Changed

`git diff --stat 79619a5...HEAD` (agent/wallet-goal-deploy, includes the
fee-fix commit): 16 files, +1001/−59. Headlines:

- `lovecash/bch/goalshow.py` — exact claim fee (tx size at 1 sat/byte,
  cap-guarded at the covenant's 1000) + `verify_genesis_tx`
- `lovecash/bch/tokens.py` — `tx_input0_txid` helper
- `lovecash/server/app.py` — `POST /api/goal_show` (authed), `GET /api/height`
- `lovecash/triggers/payment.py`, `core/orchestrator.py` — `raw_transaction`,
  `attach_goal_show` (hot-attach, no restart)
- `contracts/web/deploy_tx.mjs` + test, `deploy_ui.js`, `ui.js` (new bundle
  entry), rebuilt `pledge.bundle.js`
- `tests/test_goalshow.py` — +9 tests (verify unit + endpoint)
- docs: covenant-goal-shows.md, performers.md, contracts/README.md

### Commands Run

- `uv run python -m compileall lovecash tests` / `ruff check .` / `mypy` /
  `uv run --extra server pytest -q`
- `docker run --rm -v "$PWD/contracts:/w" -w /w node:22-alpine sh -c "npm test"`
  (43 JS tests) and `npm run build-web` (bundle 743 KB)
- cashscript-py spike: isolated venv (`uv venv`, Python 3.13),
  `pip install cashscript-py`, golden-fixture comparison script

### Outcome

- Tests: pass (177 Python, 44 JS)
- Lint: pass
- Build: pass (mypy clean; esbuild bundle rebuilt and checked in)
- **Chipnet e2e: PASSED.** Scripted: deploy_tx genesis broadcast accepted,
  relay verify+persist+hot-attach OK, pledge over goal → auto-claim with
  exact fee (495 bytes / 495 sats to performer P2PKH). Manual (real
  Cashonize, WizardConnect): pairing, signing prompt, and deploy PASSED
  after the fixes below (goal 1M sats, pot live, watching).

### Notes

- **cashscript-py is blocked upstream (verified, not assumed):** it pins
  `coincurve~=21.0.0`, which has no Python 3.14 wheel, and its sdist build
  crashes on cffi 2.x PEP 639 metadata (`hatch_build.py` demands a top-level
  LICENSE in cffi's dist-info). coincurve main prepares 22.0.0 with 3.14
  support — unreleased, and cashscript-py would need to relax its pin.
  Spike results (byte-identical claim tx vs the JS golden, CashTokens
  first-class) are parked in WIP commit on `agent/cashscript-py-swap`.
  Revisit when coincurve 22 ships.
- The JS swap being blocked did NOT block the deploy feature: the genesis
  tx needs the wallet's P2PKH signature anyway, so it lives in the browser
  bundle beside the pledge/refund builders.
- Hot-attach replaced the planned restart-on-deploy (~15 lines, reuses the
  existing subscribe path; `_subscribe_all` re-subscribes `_pot_sh` on
  reconnect).
- Deploy fee exactness: placeholder unlocker ships an empty scriptSig; the
  wallet adds exactly 100 bytes (66 sig push + 34 pubkey push). cashscript's
  build() refuses fee/byte < 1, so the sizing dry run carries the 1000-sat
  ceiling.
- **Found in e2e (real bugs, all fixed):**
  1. `deploy_tx.mjs` dropped the `vout === 0` parent filter — CHIP-2022-02
     allows token genesis only from outpoint index 0; the node rejected the
     wallet tx with `bad-txns-token-invalid-category`. Scripted test had
     passed by luck (faucet UTXO at vout 0). Now enforced in the JS builder,
     `verify_genesis_tx`, and the `/api/broadcast` pre-flight check.
  2. Deploy UI derived the address prefix from the tip address (always
     mainnet) → mislabeled chipnet as `bitcoincash:`. Relay now detects the
     chain from `server.features` genesis hash (`GET /api/status.network`).
  3. Deploy UI lacked the pledge flow's "Forget this wallet" escape hatch
     for stale WizardConnect sessions, and the pairing-link paste option
     (macOS Cashonize web needs paste, not QR).
  4. Deploy flow is now `broadcast:false`: wallet signs, the RELAY
     broadcasts (`POST /api/broadcast`, with a token-category pre-flight
     check) — wallet-broadcast raced genesis registration and hid the
     signed bytes when the node rejected.
- Follow-ups: real-fee treatment for the JS refund builder (still flat
  1000); multi-show concurrency (one show at a time enforced in the UI);
  remove-goal-show flow (currently: edit config.yaml + restart);
  WizardConnect relay churns on page-hide (response delivery survives via
  re-subscribe, but the UX blips).
