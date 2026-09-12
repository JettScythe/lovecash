# 2026-09-11 — Covenant shows chipnet re-test (PR #11)

- Date: 2026-09-11
- Base branch: main (PR #11 head)
- Working branch: agent/goal-show-covenant
- Model: Kimi K3

## Goal

PR comment said the contract changed since the last chipnet pass and
`chipnet_e2e.mjs` had NOT been re-run. Re-test the full covenant lifecycle
on real chipnet consensus — a few shows this time — with performer payouts
going to a fixed external address (`bchtest:qreytkxgddp4kvtc2rwqd36yux999rza7u7z05c6du`),
including the new lovecash watcher auto-claim (the headline feature).

## Files Changed

Test-only, all uncommitted at time of writing:

- `contracts/chipnet_shows.mjs` — multi-show driver (deploy / pledge / claim /
  refund / negclaim / status), genesis-is-seed flow copied from chipnet_e2e.mjs,
  payout locked to the external TARGET address.
- `config.chipnet-shows.yaml` — throwaway config pointing the watcher at show 1.
- `contracts/.chipnet-shows.json` — run state (txids, categories; no secrets).

## Commands Run

- `docker run --rm -v $PWD/contracts:/w -w /w node:22-alpine node chipnet_shows.mjs <cmd>`
  (host has no node; node_modules pre-installed via npm ci)
- `uv run lovecash serve -c config.chipnet-shows.yaml`

## Outcome (chipnet, real consensus via chipnet.imaginary.cash)

Tests: not applicable (manual on-chain run)
Lint: pass (mypy fix b02108d earlier this session)
Build: not applicable

- **Show 1 — auto-claim by the lovecash watcher (goal 100,000):** pot seeded
  5,000; server saw 5,000 sats; pledged 96,000 (tx 3b11cf54…); watcher logged
  "Goal met — pot auto-claimed to performer: 49ba4396…" using the pure-Python
  builder in `lovecash/bch/goalshow.py`. Pot 0. Payout 100,000 sats confirmed
  at TARGET. **Headline PR feature proven on real consensus.**
- **Show 2 — manual claim (goal 8,000):** pledged 5,000 (tx 134e6aee…),
  permissionless claim via cashscript (tx 036682fc…) paid 9,000 sats to TARGET.
- **Show 3 — refund + negative (goal 500,000, deadline 1,000 blocks past):**
  pledged 5,000 (tx 84d1573e…), refunded via receipt NFT (tx f42fe815…, pot
  back to 5,000 seed), then a raw below-goal claim was **rejected by the node**
  (mandatory-script-verify-flag-failed, code 16) — consensus enforcement, not
  local VM.
- TARGET final balance: 109,000 sats in 2 utxos (both claim payouts).

## Notes

- Two driver bugs fixed mid-run, both in the new script only, not in
  shipped code: BigInt/number mix on JSON-round-tripped change utxo, and
  `BigInt(hexStr)` parsing the receipt amount as decimal (needed `0x` prefix).
- Killed a stale `lovecash serve` (PID 755, yesterday's chipnet-test config)
  that held port 8080.
- Show 3's pot still holds the 5,000-sat seed (locked as dust by design on an
  unmet show); show 1's pledge receipt NFT (96,000 sats committed) is
  refundable only after deadline 423055 — throwaway chipnet funds.
- PR comment's "re-run on chipnet before mainnet" gate: now satisfied for
  pledge/claim/refund/auto-claim; browser wallet pairing was NOT re-tested.
