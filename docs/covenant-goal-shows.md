# Covenant Goal Shows — Design (Phase 3)

Status: **design only — no code.** All-or-nothing tip goals enforced by a
BCH covenant instead of by trust: if the goal is met by the deadline, the
performer can claim the pot; if not, every pledger can claim their own
refund. lovecash's role stays watch-only: display progress, trigger toys.

## Why a covenant

Today's goal bar (`alerts.goal_sats`) is a promise: tips go to the
performer regardless of whether the goal is met. A covenant makes the
promise structural — funds are encumbered by contract rules, not by the
performer's word. This matches lovecash's non-custodial model: the
contract holds the funds, nobody holds keys.

## Contract sketch

One covenant instance per goal show. Parameters fixed at deployment:

- `goal_sats` — target total
- `deadline` — block height or timestamp (`CLTV`-style check)
- `performer_pkh` — where a met goal pays out

**Pledging.** A viewer sends a pledge output to the covenant and receives
back an immutable **receipt NFT** (same category, minted by the
covenant's minting NFT held in the covenant itself). The receipt's
commitment encodes the pledger's refund pubkey hash and pledge amount.
Receipt = proof of pledge, spendable by the pledger's wallet.

**Claim (goal met).** After total pledged ≥ `goal_sats`, anyone can
construct the settlement transaction spending all pledge outputs to the
performer address. The covenant enforces: outputs pay `performer_pkh`,
total input value ≥ goal, receipts are burned or returned. Settlement
needs no lovecash involvement — it's anyone-can-build.

**Refund (deadline passed, goal unmet).** After `deadline`, a pledge
output + its receipt NFT can be spent back to the pledger's address
encoded in the receipt commitment. Individual, permissionless refunds.

## Hard problems (flagged honestly)

1. **Refund UX.** No mainstream wallet knows how to spend a receipt NFT
   into a refund. Needs a small web refund tool (scan/paste txid → build
   + sign → broadcast). Without this, refunds are theoretical.
2. **Settlement transaction size.** All pledge inputs in one tx — the
   100 KB standardness cap bounds pledges per show (roughly a few
   hundred). Fine for a cam show; document the cap.
3. **Dust and fees.** Each pledge output needs dust + fee margin; the
   covenant must tolerate fee skimming on claim.
4. **Covenant correctness is money-critical.** This contract holds real
   viewer funds. It gets a dedicated audit pass and chipnet testing
   before any mainnet config ships. Consider this the project's first
   `deep-review` candidate.
5. **Partial-goal upgrades.** Letting a performer forfeit-to-refund early
   ("show cancelled") adds a third path; keep v1 binary.

## lovecash integration (when built)

- Config: `goal_show:` block — covenant address + goal + deadline.
  lovecash derives the scripthash and watches it like any address, but
  tags events as pledges, not tips: overlay goal bar fills from covenant
  balance, no toy trigger on pledge (or a small acknowledgment rule).
- On settlement: the performer's normal tip watcher sees the payout as
  an ordinary confirmed payment — existing pipeline, unchanged.
- The `/tip` page gets a pledge mode: builds the covenant transaction
  client-side (viewer's wallet signs) instead of a plain BIP21 QR.

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
