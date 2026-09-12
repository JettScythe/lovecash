# Goal-show covenant (Phase 3)

CashScript covenant for all-or-nothing tip goals (see docs/covenant-goal-shows.md).
Constructor: `(performerPkh, goalSats, deadline, category)` — one instance per show,
bound to one token category. The pot UTXO carries the category's minting NFT;
`pledge(bytes20 pledgerPkh)` grows the pot and mints an immutable receipt NFT (pkh only —
wallets sign plain P2PKH, min pledge 5000 sats), `claim` pays the performer once the goal
is met (permissionless — lovecash auto-broadcasts it, see `lovecash/bch/goalshow.py`),
`refund()` pays a pledger back after the deadline if the goal was missed (argless: the
receipt's own P2PKH input proves ownership; the payout is locked to the committed pkh).

Viewer pledge flow: browser bundle talks to Cashonize via **WizardConnect** (Nostr relay,
no WalletConnect project id). After any contract change: `npm run build-web` (docker) then
`cp contracts/web-dist/pledge.bundle.js lovecash/server/ui/static/pledge.bundle.js`.
Refunds run through the same bundle: it lists the viewer's receipt NFTs and builds the
refund tx (only the receipt input needs the wallet's signature).

Deploy flow (chipnet_e2e.mjs): genesis IS the seed — one transaction creates the minting
NFT directly into the covenant, so verifying a show is a one-tx check (exactly one token
output, the minting NFT, locked to the covenant). Never split mint-then-seed: the gap
lets the deployer forge receipts to their own pkh. Seed >= 678 sats (token dust floor).

Trust summary: abandonment protection only — the performer can always self-fund a claim,
even after the deadline (CLTV gives no upper bound); pledgers should refund promptly when
the window opens (first-seen relay wins the race). See docs/covenant-goal-shows.md.

Compile: `docker run --rm -v "$PWD/contracts:/w" -w /w node:22-alpine sh -c "npm install --no-audit --no-fund && npx cashc goal_show.cash -o goal_show.json"`
Test:    `docker run --rm -v "$PWD/contracts:/w" -w /w node:22-alpine sh -c "npm install --no-audit --no-fund && npm test"`
Address: `node address.mjs '{"performerPkh":"<40 hex>","goalSats":100000,"deadline":900000,"category":"<64 hex RAW order>"}'`
         (same docker invocation with `node address.mjs ...`; `category` is reversed display hex)
