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

- **Chipnet pass: DONE (same day).** `contracts/chipnet_e2e.mjs` ran the
  full lifecycle against real chipnet consensus via
  `ElectrumNetworkProvider` on `chipnet.imaginary.cash`:
  - Instance A: genesis (single minting NFT) → seed → pledge (receipt
    commitment byte-verified on-chain) → claim at goal → pot consumed.
    Claim tx `bb1b9f395b6f…3251f`.
  - Instance B (deadline=1): genesis → seed → pledge (locktime 0) →
    refund (locktime 1, CLTV) → pledger repaid, pot reduced. Refund tx
    `e272f833bba3…73730`.
  - Below-goal claim rejected **by the node**:
    `mandatory-script-verify-flag-failed` (code 16).
  - Zero VM drift vs the mock network; surprises were operational
    (builder local-eval masks node rejection — use `sendRawTransaction`
    for negative tests; cashscript's default chipnet server is dead, use
    imaginary.cash; vout-0 parent hygiene for genesis).
- **lovecash integration (round 2, same day):** shipped — `goal_show`
  config, watcher pot subscription (outside the tip pipeline), relay
  `goal_pot` broadcast, overlay goal bar tracks the pot, `/api/status`
  exposes it, `contracts/address.mjs` derives covenant addresses, and
  cashaddr learned P2SH32/token-aware P2SH32 (cross-checked against
  cashscript-derived vectors). 154 Python tests pass. **Open:** `/tip`
  pledge mode (client-side covenant tx building, viewer wallet signs).
- Byte-order: `category` constructor param takes raw serialized order
  (reversed display hex) — tooling must handle this or deployments will
  silently target the wrong category.
- Deferred: parallel per-pledge UTXOs (kills the refund-censorship grief
  vector), state-machine seal/close phase (would make "goal met by
  deadline" consensus-true instead of honesty-framed).

## Round 3–4 (same day): wallet pledging

- **WizardConnect answer (user asked):** Riften Labs' HD-aware protocol
  (Cauldron), reuses the same WC2-BCH transaction object + `inputPaths`.
  Cashonize target uses BCH WalletConnect (wc2-bch-bcr); WizardConnect
  is additive later.
- **Contract change:** `pledge(bytes20 pledgerPkh)` — receipt commitment
  only needs the address hash, so wallets sign plain P2PKH inputs (no
  contract-input pubkey placeholder, which not all wallets fill).
  Re-proven on chipnet end-to-end; node still rejects below-goal claims.
- **Server APIs:** `/api/goal_pot` (pot UTXO + token data + deadline +
  wc_project_id), `/api/utxos` (server-agnostic: plain listunspent +
  our own raw-tx token parse), `/qr-data.png` (pairing QR).
- **Browser flow:** `contracts/web/pledge_tx.mjs` (pure builder,
  6 node tests incl. full mock-VM evaluation; 31/31 node total) +
  `pledge_ui.js` → 1.1MB esbuild bundle committed at
  `lovecash/server/ui/static/pledge.bundle.js` (rebuild after every
  cashc recompile — artifact is inlined).
- **Manual gate: PASSED 2026-09-10 with real Cashonize on chipnet.**
  Pairing → sign → broadcast → covenant enforcement all confirmed;
  pledge tx 8acacaf6…c9b2 grew the pot 10,000→10,700 with a
  byte-exact receipt commitment (pkh ++ le64(700)). Bugs found only by
  this live test: init crashed decoding the P2SH32 pot as P2PKH;
  Node Buffer in browser code; dummy provider hardcoded mainnet
  (rejected bchtest outputs); qrUri (QR-only encoding) shown as paste
  text; zombie relay process serving stale bundle with wrong MIME;
  Fulcrum include_tokens filter hiding token UTXOs. All fixed and
  regression-tested same day.
