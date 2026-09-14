# 2026-09-11 — Goal-show auto-settle + covenant hardening (PR #11 follow-up)

- Date: 2026-09-11
- Base branch: main (post PR #10 merge)
- Working branch: agent/goal-show-covenant (rebased onto main; one conflict in
  tests/test_token_tips.py — both sides appended tests, kept both)
- Model: Kimi K3 (main)

## Goal

Implement the owner's decisions after the deep-review of PR #11:

1. Auto-settlement: claim auto-broadcast when pot >= goal; refunds as close to
   automatic as the non-custodial design allows.
2. Thresholds against dust DoS: min pledge, min goal, refunds subtract fees.
3. Fold in the truncated deep-review's late findings (genesis forgery window,
   false "harmless" comment, 546-receipt fee squeeze).

## What changed

- `contracts/goal_show.cash`:
  - `refund(sig, pubkey)` → `refund()`. The covenant checkSig was redundant:
    the receipt NFT lives at the pledger's P2PKH address, so spending it
    already requires their key; the payout is locked to the committed pkh.
    Side benefit: covenant input shrank ~106 bytes, killing the 546-receipt
    fee-stuck edge.
  - Min pledge 546 → 5000 sats (covers refund fee, kills dust DoS).
  - Fixed the false "late pledge is harmless" comment — CLTV gives no upper
    bound; post-deadline top-up can brick refunds. Mitigation documented.
  - Header now mandates one-tx genesis+seed.
- `lovecash/bch/goalshow.py` (new): pure-Python claim-tx builder.
  Golden-tested byte-identical against cashscript TransactionBuilder output.
  Verifies the constructed redeem script hashes to the configured pot address
  before returning. Caught a real bug during development: P2SH32 payload is
  hash256 (DOUBLE sha256), not single.
- `lovecash/triggers/payment.py`: `_maybe_auto_claim` — after each pot balance
  report, if pot >= goal, build + broadcast the permissionless claim (one
  attempt per pot outpoint; failures degrade to a log line).
- `lovecash/config.py`: `MIN_GOAL_SATS = 100_000` on GoalShowConfig +
  performer_pkh 40-hex validation.
- `contracts/chipnet_e2e.mjs`: genesis IS the seed (single tx, minting NFT
  created straight into the covenant) — closes the forged-receipt window the
  deep review found in the split mint-then-seed flow.
- `contracts/web/refund_tx.mjs`: argless refund, only the receipt input signs
  (`inputPaths: [[1, 'receive', 0]]`).
- `contracts/web/pledge_ui.js` + `lovecash/server/ui/tip.py`: honest copy —
  auto-claim, one-tap refunds, "refund promptly" disclosure, min pledge 5000.
- Docs: covenant-goal-shows.md trust assumptions rewritten (post-deadline
  top-up, one-tx genesis, refund UX solved); contracts/README.md updated.
- pledge.bundle.js rebuilt (new artifact + copy inlined).

## Honest limitation (conveyed to owner, accepted)

Refunds can never be fully automatic: receipts live in pledger wallets, so a
pledger signature is always required. Auto-claim is fully automatic (no sigs).

## Commands run

- `docker run --rm -v $PWD/contracts:/w -w /w node:22-alpine node_modules/.bin/cashc ...`
- `docker run ... node --test` (38 JS tests)
- `uv run pytest tests/ -q`, `uv run ruff check lovecash/ tests/`, `uv run mypy lovecash/`

## Outcome

- Tests: pass (166 Python, 38 JS incl. 25 covenant mock-network)
- Lint: pass
- Build: pass (cashc compile + esbuild bundle)

## Notes / follow-ups

- NOT re-run on chipnet: chipnet_e2e.mjs was updated for the new flow but not
  executed against the network (needs a funded throwaway key). Run
  `node chipnet_e2e.mjs` before mainnet; the previously deployed chipnet pot is
  stale (contract bytecode changed → address changed).
- The post-deadline top-up race is mitigated (auto-claim + prompt refunds +
  first-seen relay), not eliminated; the mutable-latch `fail()` state machine
  remains the documented upgrade path if it ever matters.
- GoalShowConfig min goal is app-level only — constructor params can't be
  validated on-chain.
