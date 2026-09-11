# Covenant Goal Shows — Design (Phase 3)

Status: **design only — no code.** All-or-nothing tip goals enforced by a
BCH covenant instead of by trust: if the goal is met by the deadline, the
performer can claim the pot; if not, every pledger can claim their own
refund. lovecash's role stays watch-only: display progress, trigger toys.

## Why a covenant

Today's goal bar (`alerts.goal_sats`) is a promise: tips go to the
performer regardless of whether the goal is met. A covenant replaces part
of that promise with structure — **abandonment protection**: funds in the
pot can leave only as a whole-pot claim by the performer (goal met) or as
individual refunds after the deadline (goal missed). The contract holds
the funds; nobody holds keys. What it does NOT do is prove the goal was
met by genuine audience demand — the performer can always self-fund the
shortfall and claim (see Trust assumptions below).

## Contract sketch

One covenant instance per goal show. Parameters fixed at deployment:

- `goal_sats` — target total
- `deadline` — block height or timestamp (`CLTV`-style check)
- `performer_pkh` — where a met goal pays out

**Pledging.** A viewer pledges by spending the pot UTXO into a larger
pot and receives back an immutable **receipt NFT** (same category,
minted via the pot's minting NFT held in the covenant itself). The
receipt's commitment encodes the pledger's refund pubkey hash and pledge
amount. Receipt = proof of pledge, spendable by the pledger's wallet.

**Claim (goal met).** Once the pot's value ≥ `goal_sats`, anyone can
build the one-input settlement transaction paying the whole pot (minus
fee) to `performer_pkh`; the minting NFT is burned with the pot.
Settlement needs no lovecash involvement — it's anyone-can-build.

**Refund (deadline passed, goal unmet).** After `deadline`, while the pot
is below goal, the pot + one receipt NFT can be spent back to the
pledger's address encoded in the receipt commitment. Individual,
permissionless refunds, serialized on the pot UTXO.

## Trust assumptions (v1)

The covenant enforces abandonment protection, not honesty about demand:

- **Performer self-funding.** A performer can always top up the pot with
  their own sats and claim. Pre-deadline this is economically identical
  to the performer tipping themselves — treated as a feature; reputation
  is the real guardrail. **Post-deadline it is sharper:** because BCH
  enforces only time *lower* bounds (CLTV), pledge()'s `locktime <
  deadline` is a declared bound, not an enforced one — a late pledge can
  push an underfunded pot over goal, brick pending refunds, and claim
  everything at zero net cost (the top-up comes back in the payout).
  Mitigation, not elimination: lovecash auto-claims the moment the pot
  reaches goal, and refunds open at deadline+1 — pledgers who refund
  promptly win the race by first-seen relay policy. Pledgers should
  treat "refund at the deadline" as a duty, not an option.
- **Genesis verification (hard assumption).** Pledgers (or the client
  tooling) MUST verify the goal-show category's genesis. The supported
  flow — `chipnet_e2e.mjs --deploy` — makes the genesis transaction ALSO
  the seed: the minting NFT is created directly into the covenant
  (category = parent outpoint txid, computable pre-broadcast), so
  verification collapses to one tx: exactly one token output, the
  minting NFT, locked to the covenant. A split mint-then-seed flow
  leaves a window where the performer can mint forged receipts to their
  own pkh and drain other pledgers' refunds later — never deploy that
  way. Note the covenant binds the category in raw serialized byte
  order — the reverse of what wallets/explorers display.
- **One category per show.** Receipts are bound to the token category,
  not to a covenant instance. Reusing a category across shows lets old
  receipts refund against a new show's pot. Footgun: don't.
- **Serialized pot.** Pledges and refunds race on the single pot UTXO;
  losers rebuild on the new pot. Fine against ordinary contention, but a
  dedicated griefer with one small receipt can censor refunds at one
  tx-fee per block. Parallel per-pledge UTXOs are the documented upgrade
  path if contention ever matters.

## Hard problems (flagged honestly)

1. **Refund UX.** Solved for v1: the `/tip` page lists the viewer's
   receipt NFTs and builds the refund tx (WizardConnect → Cashonize
   signs). refund() takes no covenant signature — the receipt's own
   P2PKH input proves ownership and the payout is locked to the
   committed pkh, so anyone can trigger a refund but only the rightful
   pledger can be paid. Refunds can never be fully automatic: the
   receipt lives in the pledger's wallet, so their signature is always
   required — that's the non-custodial deal.
2. **Serialized refunds.** Settlement is one input (claim spends only the
   pot), so the old 100 KB settlement-cap concern is gone. The real
   scaling cost is refunds: N pledges = N serialized refund transactions
   racing on the pot UTXO, plus the censoring vector above. Fine for a
   cam show; document the limit.
3. **Dust and fees.** Each pledge output needs dust + fee margin; the
   covenant must tolerate fee skimming on claim.
4. **Covenant correctness is money-critical.** This contract holds real
   viewer funds. It gets a dedicated audit pass and chipnet testing
   before any mainnet config ships. Consider this the project's first
   `deep-review` candidate.
5. **Partial-goal upgrades.** Letting a performer forfeit-to-refund early
   ("show cancelled") adds a third path; keep v1 binary.

## lovecash integration

- **Done:** `goal_show:` config block (covenant token address + goal).
  lovecash subscribes the pot's scripthash alongside the xpub addresses,
  but pot changes only refresh the overlay goal bar — pledges are not
  tips and never trigger toys. Derive the address with
  `contracts/address.mjs` (dockerized node; see contracts/README.md).
- **Auto-claim:** the moment the watched pot balance reaches the goal,
  the relay builds and broadcasts the permissionless claim tx itself
  (`lovecash/bch/goalshow.py`, golden-tested byte-for-byte against
  cashscript's TransactionBuilder). The performer is paid without
  touching a wallet; on any failure they can still claim manually.
- On settlement: the performer's normal tip watcher sees the payout as
  an ordinary confirmed payment — existing pipeline, unchanged.
- **Open:** the `/tip` page pledge mode: builds the covenant transaction
  client-side (viewer's wallet signs) instead of a plain BIP21 QR.
  Done so far: the `/tip` page shows the live pot progress bar, pot
  address, and the refund promise; wallet pledging itself is blocked on
  the transport decision below.

## Wallet transport (decision record, 2026-09-10)

Viewer pledging needs the browser to build a covenant tx and a wallet to
sign it. Surveyed options:

- **CashConnect** (`cashconnect` npm, v0.0.25): WalletConnect v2 with
  CashRPC methods, Cashonize reference integration. Problems: the
  dapp-integration API is undocumented ("TODO" in its own readme), it
  needs a WalletConnect Cloud project ID (centralized relay), and
  adoption is early. Building the viewer flow on it now is building on
  mud.
- **Raw-tx handoff**: no common wallet imports unsigned covenant txs
  with dapp-chosen inputs; the builder needs the viewer's UTXOs, which
  no read-only channel provides. Dead end without wallet comms.

**Decision:** defer signing integration until a concrete wallet target
(Paytaca vs Cashonize) is confirmed by performer demand. The pledge-tx
builder (cashscript `TransactionBuilder`, proven on chipnet in
`contracts/chipnet_e2e.mjs`) is the reusable core either way — the
transport is a thin layer over it. When picked, CashConnect is the
default candidate; re-verify its dapp-side API maturity first.

## Dependencies to evaluate at implementation time

- CashScript (JS) for the contract artifact, or hand-rolled bytecode via
  Libauth templates — decide then; both are mature.
- BCMR entry for the receipt NFT category so wallets render receipts
  legibly.

## Open questions

- Should toys react per-pledge, or only at settlement? (Per-pledge small
  reactions keep engagement; settlement-only is simpler and matches the
  trust story.)
- Multi-show concurrency: one covenant per show implies deploy/teardown
  tooling. A reusable "goal factory" covenant is possible but out of v1.
