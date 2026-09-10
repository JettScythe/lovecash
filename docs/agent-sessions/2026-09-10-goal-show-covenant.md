# Session: Goal-show covenant (Phase 3, contract only)

- Date: 2026-09-10
- Base branch: `main` (via `agent/cashtoken-tips`)
- Working branch: `agent/goal-show-covenant`
- Models: Kimi K3 (lead) → specialist (contract implementation, 2 rounds)
  → deep-review (adversarial contract review) → specialist (fixes)

## Goal

Implement the all-or-nothing goal-show covenant designed in
`docs/covenant-goal-shows.md` — pot with receipt-NFT refunds, no keys
anywhere.

## What shipped

- `contracts/goal_show.cash` — `GoalShow(performerPkh, goalSats,
  deadline, category)` with `pledge` / `claim` / `refund`.
- `contracts/goal_show.test.mjs` — 25 MockNetworkProvider tests,
  including an index-shift adversarial harness.
- `contracts/README.md` + `package.json` — dockerized node toolchain
  (host has no node/npm); compile + test via `node:22-alpine`.
- `docs/covenant-goal-shows.md` — trust story corrected: the covenant
  protects against *abandonment*; a performer can always self-fund the
  shortfall and claim (economically = tipping themselves). Genesis
  minting-exclusivity documented as a client-side trust assumption, incl.
  the constructor-param byte-order landmine (raw order = reversed display
  hex).

## Process notes (why the diff looks like this)

Deep review executed four **critical** exploits against the first draft —
all traceable to one root cause: absolute `tx.inputs[0]` references
without `this.activeInputIndex` binding. Also found: sign-bit-negative
receipt amounts (`OP_BIN2NUM` on 8 LE bytes), unbounded refund inputs,
dust-floor-bricked last refund, and a false "harmless" claim about
post-deadline pledges (self-funded claims brick other pledgers' refunds).
All fixed or honestly documented per the deep-review report; one review
suggestion (`<=` on pot continuation) was itself wrong-direction and was
implemented as `>=` with a test pinning why.

## Commands run

- `docker run --rm -v "$PWD/contracts:/w" -w /w node:22-alpine sh -c
  "npm install --no-audit --no-fund && npm test"` — **25/25 pass**
  (reproduced by lead after each specialist round)

## Outcome

Tests: pass (25/25, mock network)
Lint: not applicable (no Python changed; repo ruff untouched)
Build: artifact `goal_show.json` compiles via cashc 0.13.2

## Notes / follow-ups

- **Chipnet pass required before mainnet** — mock VM ≠ consensus. Deploy
  + pledge + claim + refund on chipnet with real wallets is the next gate.
- **lovecash integration not started**: watcher-side pledge detection,
  overlay goal bar from pot balance, `/tip` pledge-mode tx building
  (client-side, viewer wallet signs) remain open.
- Byte-order: `category` constructor param takes raw serialized order
  (reversed display hex) — tooling must handle this or deployments will
  silently target the wrong category.
- Deferred: parallel per-pledge UTXOs (kills the refund-censorship grief
  vector), state-machine seal/close phase (would make "goal met by
  deadline" consensus-true instead of honesty-framed).
