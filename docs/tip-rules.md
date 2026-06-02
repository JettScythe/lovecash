# Tip Rules Guide

Your tip rules are your menu: they decide what each tip amount does to
your toy. You set them in `config.yaml`.

## How rules work

Each rule says: "if a tip is between X and Y satoshis, do this action at
this strength for this long." A satoshi is the smallest unit of Bitcoin
Cash. 100,000,000 satoshis = 1 BCH.

When a tip arrives, lovecash finds the matching rule and triggers your
toy. If a tip matches more than one rule, the highest tier wins.

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
    min_confirmations: 1
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
| min_confirmations | Optional. Wait for this many blockchain confirmations before firing. Use on big tiers. |

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

## Confirmations: protecting against unconfirmed tips

For small tips, lovecash acts instantly (0 confirmations) so the
experience feels responsive. For large tips, you can require
`min_confirmations: 1` so the payment is locked into the blockchain
before your toy reacts. This prevents a rare trick where someone sends a
big payment and then cancels it before it confirms.

Rule of thumb: leave small tiers at 0 confirmations, set big tiers
(say over 50,000 sats) to require 1.

## Hard limits override every rule

In your`limits` section:

```yaml
limits:
  max_strength: 12
  max_duration_s: 30
```

Even if a rule asks for strength 20, it's capped to your`max_strength`.
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

When the queue gets too long (longer than`max_queue_seconds`), the
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

After editing`config.yaml`, restart lovecash to load the changes.
