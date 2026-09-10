# Goal-show covenant (Phase 3)

CashScript covenant for all-or-nothing tip goals (see docs/covenant-goal-shows.md).
Constructor: `(performerPkh, goalSats, deadline, category)` — one instance per show,
bound to one token category. The pot UTXO carries the category's minting NFT;
`pledge` grows the pot and mints an immutable receipt NFT, `claim` pays the performer
once the goal is met, `refund` pays a pledger back after the deadline if the goal was missed.

Trust summary: abandonment protection only — the performer can always self-fund a claim
(equivalent to tipping themselves). Pledgers must verify off-chain that genesis minted
exactly one minting NFT and it sits in the pot. Seed the pot with >= 678 sats (token dust floor).

Compile: `docker run --rm -v "$PWD/contracts:/w" -w /w node:22-alpine sh -c "npm install --no-audit --no-fund && npx cashc goal_show.cash -o goal_show.json"`
Test:    `docker run --rm -v "$PWD/contracts:/w" -w /w node:22-alpine sh -c "npm install --no-audit --no-fund && npm test"`
Address: `node address.mjs '{"performerPkh":"<40 hex>","goalSats":100000,"deadline":900000,"category":"<64 hex RAW order>"}'`
         (same docker invocation with `node address.mjs ...`; `category` is reversed display hex)
