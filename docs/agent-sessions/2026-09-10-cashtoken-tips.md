# Session: CashToken tips (Phases 1–3)

- Date: 2026-09-10
- Base branch: `main`
- Working branches: `agent/cashtokens-research` → `agent/cashtoken-tips`
- Model: Kimi K3 (main agent, no delegation)

## Goal

A public X thread compared lovecash to a closed-source PulseChain
alternative whose claimed edge was liquidity-pool integration and no
private keys. lovecash already holds no keys; the task was to research
what BCH CashTokens/covenants/pools could add, then implement it.

User decisions: research writeup first, **per-category token rules**,
then "get to work" on all phases with me leading.

## What shipped

- **Phase 1 — CashToken tip detection.** Token-aware cashaddr kinds 2/3
  (`z…` addresses share kind-0 scripts), a pure-Python CHIP-2022-02
  token-prefix parser (`bch/tokens.py`, observer-only — parse failure
  degrades to "no tokens", never touches the sats path), `TokenRule` /
  `TokenReceipt` models, per-category rules in the engine, dual raw-hex
  fetch in the watcher only when token rules exist, `require_conf: true`
  default gating token tips to 1 confirmation, token-aware tip address on
  QR/URI endpoints when rules are configured, dashboard live-edit of
  `token_rules`.
- **Phase 2 — fan-token UX.** `/tip` page token menu (category hex, min
  amount, Cauldron link, copy button), overlay alerts + dashboard recent
  tips show token receipts, `/api/status` exposes a public `token_menu`,
  performer docs (`docs/fan-tokens.md`) covering minting in Electron
  Cash, BCMR, and Cauldron LP seeding.
- **Phase 3 — design only.** `docs/covenant-goal-shows.md`: all-or-
  nothing goal covenant sketch with receipt-NFT refunds, plus the hard
  problems (refund UX, settlement tx size, audit requirement).

## Files changed

`git diff --stat main...HEAD`: 24 files, +1311/−43. Includes the
research writeup commit from `agent/cashtokens-research`.

## Commands run

- `uv run ruff check .` — pass
- `uv run --extra server pytest -q` — 147 passed (31 new: CHIP test
  vectors, synthetic tx parsing, per-category rule matching, watcher
  integration incl. require_conf gating)
- `uv run python -m compileall lovecash` — pass
- Live validation (post-implementation): lovecash's own `ElectrumClient`
  against `fulcrum.jettscythe.xyz`, fetching raw hex via
  `blockchain.transaction.get` (no verbose flag) for 177 real mainnet
  txs from the 3 tip blocks, parsed with `bch/tokens.py`: **343 token
  outputs found**, including mutable-NFT commitments and FT amounts near
  the VM max (`72624976668141661`). No parse failures.

## Outcome

Tests: pass (147)
Lint: pass
Build: pass (package rebuild via uv on each run)
Live mainnet parse: pass (177/177 txs, 343 token outputs)

## Notes

- **BCMR auto-resolution deferred (YAGNI):** needs a per-category
  registry URL config and no performer has published one. Rules key off
  category hex + base units, so nothing is blocked. Add when a real
  registry exists to test against.
- **Cauldron deep links:** cauldron.quest is a JS SPA with no verifiable
  URL scheme for a category; we link the site root and show the category
  hex for search. Verify the scheme manually if deep links are wanted.
- **Deliberate simplification:** token receipts are matched per-output,
  not summed per category across a tx's outputs. A viewer splitting one
  tip across two outputs gets two smaller matches. Sum-per-category is
  the upgrade path if a wallet ever does that.
- **DSProof for token tips:** `require_conf: false` opts into the
  existing sats-tier DSProof path, which covers tx-level double-spends,
  but token value is invisible to the sats tiers — the safe default is
  confirmation-gated. Flagged in code + docs.
- **Phase 3 caveat:** the covenant holds real viewer funds; it is this
  project's first `deep-review` candidate before any mainnet use.
- Unresolved: `/tip` "thank you" heuristic matches on sats amount, so
  token tips (dust sats) don't trigger the viewer-facing confirmation.
  Cosmetic; fix when a performer reports it.
