# Fan Tokens: tip with CashTokens

CashTokens are tokens that live directly on the Bitcoin Cash chain
(CHIP-2022-02, live since May 2023). lovecash can treat a token tip
exactly like a BCH tip: viewer sends your token, the watcher sees it
on-chain, your rules fire the toy.

Everything stays non-custodial: minting and liquidity happen in **your
wallet**, lovecash never sees a private key.

## How it works for viewers

1. You mint a token (below) and add `token_rules` to `config.yaml`.
2. Your tip QR automatically switches to a **token-aware address** (it
   starts with `z…` — same wallet, the spelling just tells wallets they
   may attach tokens).
3. A viewer sends your token from a CashToken wallet (Electron Cash,
   Paytaca, Cashonize, Zapit) to that address.
4. lovecash detects the token in the raw transaction and fires the
   matching rule. With the default `require_conf: true`, token tips fire
   after 1 confirmation — a token's value isn't visible in its satoshi
   amount, so the usual instant/DSProof tiers can't size the risk.

## Minting your token

Do this in **Electron Cash** (desktop, CashTokens built in):

1. Open the Tokens tab → "Create new token".
2. Choose a fixed supply (e.g. 1,000,000 base units). Fixed supply is
   enforced by the chain — nobody, including you, can mint more later.
3. Note the **category ID** (64 hex chars). This is the token's identity.
   Tickers can be faked; the category ID cannot.

Publishing metadata (name, ticker, decimals, icon) is done via a BCMR
registry — see the CHIP-BCMR spec. It's optional for lovecash: rules key
off the category ID and base units, not display metadata.

## Adding token rules

```yaml
token_rules:
  - name: "fan-buzz"
    category: "aa11bb22…"   # your 64-hex category ID
    min_amount: 100          # BASE units (before decimals)
    max_amount: 999
    require_conf: true       # default; wait for 1 block before firing
    action: Vibrate
    strength: 8
    duration_s: 10
```

Token rules sit alongside your sats `rules` and obey the same hard
`limits` (strength cap, duration cap, panic stop, rate limit). Highest
matching tier wins per toy, same as sats rules. You can edit them live
from the dashboard's settings panel.

## Giving the token value: liquidity pools

A token viewers can buy and sell is more fun than one they can only
receive. Seed a liquidity pool on [Cauldron](https://cauldron.quest)
(the BCH token DEX):

1. In Electron Cash, send some BCH + some of your token to the wallet
   you'll manage the pool from.
2. On Cauldron, create/add to the BCH↔your-token pool (search by your
   category ID).
3. Viewers can now swap BCH → your token on Cauldron, then tip it back
   to you. The `/tip` page shows a "Get tokens on Cauldron" link
   automatically whenever you have token rules configured.

You earn swap fees as the liquidity provider; viewers get a liquid way
in and out. That's the whole loop — no custody anywhere in it.

## Safety notes

- **Verify the category ID on a block explorer** before pasting it into
  config. A wrong hex string just means tips in the wrong token are
  ignored — but a lookalike ticker is how impersonators fish.
- Keep `require_conf: true` unless the amounts are trivial. Token tips
  carry only dust sats, so the satoshi-based 0-conf tiers know nothing
  about the value at stake.
- Token outputs carry ~546 sats of dust. If you also have sats rules
  starting at 0, a token tip may match both — set your lowest sats rule
  above the dust range if that matters to you.
