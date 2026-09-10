# CashTokens, Covenants & Liquidity Pools for lovecash

Research writeup, 2026-09-10. Status: **research only — no code changes yet.**

## Context

A PulseChain developer publicly claimed a superior version of lovecash,
citing liquidity-pool integration and no private keys as differentiators.
lovecash already holds no keys (config stores an xPub only). The real gap
worth closing: token-aware tipping plus liquidity-pool integration, using
BCH-native primitives. The demographics differ — theirs is DeFi-first,
lovecash is performer-first — but CashTokens let lovecash absorb the
token economy without changing the architecture or trust model.

## BCH primitives

### CashTokens (CHIP-2022-02, live since May 2023)

- **Fungible tokens (FT):** an `amount` per output; fixed supply set at
  genesis; freely mergeable/divisible.
- **NFTs:** a `capability` (`none` / `mutable` / `minting`) plus a 0–40
  byte `commitment`.
- **Encoding:** token prefix on transaction outputs:
  `0xef <32-byte category> <bitfield> [commitment_length commitment] [ft_amount]`
- **Token-aware cashaddr kinds:** 2 (P2PKH + tokens, `z…` addresses) and 3
  (P2SH20 + tokens, `r…`). They carry the same 20-byte hash as kinds 0/1,
  so scripthash derivation is unchanged.
- **Wallets with token support:** Electron Cash, Paytaca, Cashonize, Zapit.

### BCMR (Bitcoin Cash Metadata Registries)

- JSON registry giving a token category its ticker, decimals, icon, and
  identity metadata.
- **DNS-resolved:** `https://<domain>/.well-known/bitcoin-cash-metadata-registry.json`,
  must allow CORS `Access-Control-Allow-Origin: *`.
- **Chain-resolved:** authchain (zeroth-descendant transaction chain) with
  `OP_RETURN <'BCMR'> <sha256(registry)> [uri…]` publication outputs.
- lovecash only needs the DNS-resolved subset: fetch the well-known URI,
  key identities by category hex.

### Covenants

- Introspection opcodes (2022) + token inspection opcodes (2023) + VM
  limits / BigInt (May 2025 upgrade) enable CashScript covenants: AMMs,
  pledge contracts, all-or-nothing crowdfunds.
- A covenant holds the funds; nobody holds keys — fits the lovecash
  non-custodial model exactly.

### Liquidity pools

- **Cauldron DEX:** constant-product BCH↔token pools, CashTokens-native.
  A performer can seed a pool for their own token; viewers swap BCH→token
  and tip the token. Pools are URL-addressable per category, so
  integration on the `/tip` page is a link, not an SDK.

## Gap analysis vs current code

| Current | Needed for tokens |
|---|---|
| `cashaddr.decode` accepts kinds 0/1 only | Accept kinds 2/3; map to the same locking scripts in `to_scripthash` |
| Verbose tx decode (`blockchain.transaction.get txid true`) | Token prefix is absent from verbose output → parse raw hex outputs |
| Sats-only `PaymentTrigger` | Optional token payload (category, FT amount, NFT capability/commitment) |
| Sats-only rules | Per-category token rules, same `limits` clamps below the rules layer |
| `/tip` page is BCH-only | Cauldron swap link + token preset amounts |

No new dependencies required. The prefix parser is ~80 lines of pure
Python (CompactSize + bitfield). The DSProof / 0-conf pipeline is
unchanged: a token double-spend is a transaction double-spend.

## Feature ladder (effort ascending)

### 1. CashToken tip detection — the core

Viewer tips a whitelisted token amount → rules map amount → toy action.
An NFT of a whitelisted category acts as a membership pass (tier upgrade
while held, or an NFT riding in the tip tx unlocks a special rule).
Same safety posture: hard limits, panic stop, and rate limiting all live
below the rules layer and apply unchanged.

### 2. Fan-token economy

The performer mints a token category in Electron Cash (keys stay in their
wallet; lovecash never sees them). Docs walk through minting, publishing
BCMR metadata, and seeding a Cauldron LP. The `/tip` page gains a
"buy TOKEN" Cauldron link; the overlay shows ticker/icon from BCMR.
This neutralizes the "works with liquidity pools" claim — lovecash
performers get LP-backed tokens without lovecash touching swaps or keys.

### 3. Covenant goal shows

All-or-nothing shows: tips accumulate in a covenant; goal met → claimable
by the performer; deadline missed → refundable by viewers. Trust-minimized
goal shows are a real differentiator versus centralized platforms. This is
genuine CashScript engineering plus refund UX — design doc before any code.

## Rejected (YAGNI)

- **NFT commitment command channel** (40-byte on-chain action encoding):
  requires minting tooling viewers don't have; the OP_RETURN memo already
  covers viewer intent.
- **AnyHedge / BCHBull volatility hedging:** a financial product, not
  tipping.
- **Running an indexer (Chaingraph) or a DEX:** raw-hex parsing removes
  the indexer dependency; Cauldron links remove any DEX ambition.
- **Token→fiat/sats conversion rules:** per-category rules (chosen
  direction) keep the rules engine honest — no oracle in the toy-safety
  path.

## Risks / notes

- **Dual-fetch bandwidth:** with token rules configured, each tip costs a
  raw-hex fetch in addition to the verbose fetch. Replacing the verbose
  path with our own parser for sats too would be cleaner but rewrites a
  verified money path — dual-fetch first, consolidate later if profiling
  justifies it.
- **Dust:** token outputs carry 546+ sats of dust; a tip with tiny sats
  plus tokens is normal, not an attack. Token rules must not be confused
  by the dust value.
- **BCMR trust:** fetch over HTTPS, key everything by category hex, never
  trust the ticker alone — the category ID is the identity. A malicious
  registry means display spoofing only; no funds are at risk (non-custodial
  invariant holds).
- **0-conf tokens:** same DSProof model as BCH tips. Token rules should
  respect the existing `zeroconf_max_sats` / ceiling logic, or get their
  own per-category ceiling.

## Recommended next steps

1. **Phase 1** on a task branch: kinds 2/3 in `cashaddr.py`, a
   `bch/tokens.py` prefix parser, dual-fetch in `triggers/payment.py`,
   per-category rules in `engine/rules.py` + config, plus tests.
2. **Phase 2:** Cauldron link on `/tip`, BCMR fetch for overlay/dashboard
   display, performer docs (mint, BCMR, LP seeding).
3. **Phase 3:** covenant goal shows — separate design doc first; do not
   start from this writeup.
