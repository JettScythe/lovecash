# Tip Rules Guide

Your tip rules are your menu: they decide what each tip amount does to
your toy. You set them in `config.yaml`.

## How rules work

Each rule says: "if a tip is between X and Y satoshis, do this action at
this strength for this long." A satoshi is the smallest unit of Bitcoin
Cash. 100,000,000 satoshis = 1 BCH.

When a tip arrives, lovecash finds the matching rule and triggers your
toy. If a tip matches more than one rule, the highest tier wins.


## Multiple toys

You can connect more than one toy and give each its own rules. Declare
your toys in `config.yaml`:

```yaml
lovense:
  host: "127.0.0.1"
  port: 30010
  toys:
    - toy_id: "428ecdba..."     # device id from`lovecash doctor`
      max_strength: 15
    - toy_id: "9f2c1a..."
      max_strength: 20
```

Then target rules at a specific toy with the`toy` field. A rule with no
`toy` drives all toys:

```yaml
rules:
  - name: "both-toys"
    min_sats: 1000
    action: Vibrate # no`toy` -> every toy responds
    strength: 5
    duration_s: 3
  - name: "toy-a-only"
    min_sats: 5000
    toy: "428ecdba..."       # only this toy
    action: Thrusting
    strength: 12
    duration_s: 10
```

A single tip can drive multiple toys: if two rules (one per toy) match
the same amount, both fire. Within each toy, the highest matching tier
wins. Per-toy `max_strength`/`max_duration_s` override the global limits.

To find your toy ids, run `lovecash doctor` — it lists each connected
toy by id and name.

## A complete example

```yaml
rules:
  - name: hello
    min_sats: 500
    max_sats: 1999
    action: Thrusting
    strength: 2
    duration_s: 3
  - name: tease
    min_sats: 2000
    max_sats: 9999
    action: Thrusting
    strength: 6
    duration_s: 6
  - name: intense
    min_sats: 50000
    action: Thrusting
    strength: 18
    duration_s: 20
```

Each rule must start with a dash (`-`). The fields under it are indented.

## The fields

| Field | What it means |
|---|---|
| name | A label for you. Shows in logs. |
| min_sats | Smallest tip that triggers this rule. |
| max_sats | Largest tip for this rule. Optional; defaults to "no limit". |
| action | What the toy does. See actions below. |
| strength | Intensity, 0 to 20. |
| duration_s | How many seconds it runs. |

## Choosing the right action for your toy

Different toys use different actions. Use the one your toy supports:

| Action | Toys |
|---|---|
| Vibrate | Most vibrators (Lush, Hush, etc.) |
| Thrusting | Stroking/thrusting toys (Solace, Solace Pro) |
| Depth | Stroke range on some thrusting toys |
| Rotate | Rotating toys (Nora) |
| Pump | Inflating toys (Max) |

Not sure which your toy uses? Test it directly. With your toy connected,
run this (replace the toy id with yours from the doctor output):

```bash
curl -k -X POST https://127.0.0.1:30010/command \
  -H "Content-Type: application/json" \
  -d '{"command":"Function","action":"Thrusting:3","timeSec":2,"apiVer":1}'
```

If the toy responds, that action works. Try`Vibrate:3`,`Rotate:3`,
etc. to find what your toy does.

## Your earnings stay private

lovecash gives every tipper a fresh address derived from your xpub, so
no one can watch one address and total your income. Each session it also
automatically resumes at a never-used address, so addresses are never
reused across streams. This is fully non-custodial — lovecash holds no
keys and can never touch your funds.


### Getting your xpub

In Electron Cash: Wallet -> Information -> Master Public Key. It starts
with `xpub` and the path shown should be `m/44'/145'/0'`. Copy the xpub
only — never the seed phrase.

### How rotation works

With `rotate_on_payment: true`, the overlay QR shows a new address after
every tip. A viewer who scanned the old QR a moment ago is still fine —
lovecash keeps watching recent addresses (the gap limit window), so their
tip is still detected. Each new viewer simply sees a fresh address.

### Important: tips sent before lovecash starts

lovecash detects tips that arrive while it's running. If a tip lands
before you start lovecash (or while it's stopped), it's recorded as
existing history and will not trigger your toy. Start lovecash before
sharing your QR, and keep it running through your session.

## How tips are credited: the safety tiers

lovecash decides how fast to act on a tip based on its value and on
Bitcoin Cash's double-spend protections. Four outcomes, all set under
`bch:` in your config:

| Tip size | What happens | Why |
|---|---|---|
| At or below `zeroconf_max_sats` | Credited instantly | Too small to be worth attacking |
| Between the two thresholds | Short double-spend check, then credited if clean | Catches the common double-spend in seconds |
| At or above `always_confirm_above_sats` | Always waits for 1 confirmation | High value: a proof alone isn't enough |
| Any size, if a double-spend is detected | Waits for 1 confirmation | The payment isn't safe yet |

```yaml
bch:
  zeroconf_max_sats: 100000 # at/below: instant
  always_confirm_above_sats: 5000000  # at/above: always wait for a block
  dsproof_enabled: true # the double-spend check, on by default
  dsproof_window_seconds: 5
```

### Why high-value tips always wait

Double-spend proofs catch someone trying to spend the same coins twice on
the open network — opportunistic fraud. They do NOT protect against an
attacker with the resources to get a conflicting transaction mined
directly. For small and medium tips that's not worth anyone's effort, so
acting on the unconfirmed payment is safe and instant. For large tips the
economics change, so above`always_confirm_above_sats` lovecash always
waits for a real confirmation, even when no attack is detected. Set this
ceiling to wherever you stop being comfortable trusting an unconfirmed
payment.

### The double-spend check (dsproof_enabled)

When enabled, mid-range tips are credited the moment a short window passes
with no double-spend proof — usually a few seconds, instead of waiting
~10 minutes for a block. The overlay shows a "verifying" state during the
window. If a double-spend proof appears, the tip falls back to waiting for
confirmation. This requires an Electrum server with DSProof support
(Fulcrum has it); if yours doesn't, mid-range tips simply wait for
confirmation instead.

## Hard limits override every rule

In your `limits` section:

```yaml
limits:
  max_strength: 12
  max_duration_s: 30
```

Even if a rule asks for strength 20, it's capped to your `max_strength`.
This is your safety ceiling and it always wins. Keep it where you're
comfortable.

## When lots of tips arrive at once: playback modes

If several tips come in quickly, lovecash needs to decide how to handle
them. You control this:

```yaml
limits:
  playback: queue # or "override"
  max_queue_seconds: 30
  trim_strategy: compress  # drop_oldest | drop_newest | compress
```

- queue (recommended): tips play one after another, each in full. This
  is how Chaturbate's Lovense integration behaves. Fair to every tipper.
- override: the newest tip immediately interrupts whatever is running.
  More chaotic, less fair to earlier tippers.

When the queue gets too long (longer than `max_queue_seconds`), the
`trim_strategy` decides what to give up:

| Strategy | What happens in a tip flood |
|---|---|
| compress | Every tip still triggers, but durations shrink to fit. Nobody who paid is skipped. |
| drop_oldest | Keeps the toy responsive to recent tips; an old queued tip may be skipped. |
| drop_newest | The existing queue plays out; new tips during a backlog do nothing. |

`compress` is the fairest choice for most performers, since every viewer
who pays sees their tip do something.

## Tips for a good tip menu

- Make the lowest tier cheap so anyone can interact.
- Space tiers so the jump in intensity feels meaningful.
- Don't make your top tier instantly maximum; let viewers build up.
- Show your menu in your stream bio so viewers know what each amount
  does.

After editing `config.yaml`, restart lovecash to load the changes.

## Token rules

Rules can also match CashToken tips — see the
[Fan Tokens Guide](fan-tokens.md) for `token_rules`, which key off a
token's 64-hex category ID and base-unit amounts instead of sats. Both
rule kinds obey the same hard `limits`.
