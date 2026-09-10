# Performer Guide

This guide gets you from zero to a working tip-controlled toy on your
stream. No coding required. Budget about 20 minutes the first time.

## What you'll have when you're done

- Viewers tip you in Bitcoin Cash by scanning a QR code on your stream.
- Tips go straight to your wallet. lovecash never holds your money.
- Each tip triggers your toy based on rules you choose.
- A panic stop you control at all times.


## Before you start: what you need

1. A computer (Mac, Windows, or Linux) to run lovecash and OBS.
2. The Lovense Connect app (the one that connects your toy to a
   computer — not Lovense Remote).
3. Your Lovense toy(s).
4. A Bitcoin Cash wallet you control, such as Electron Cash. You give
   lovecash your wallet's **xpub** (Master Public Key) — never your
   seed phrase or private keys. lovecash can generate your receiving
   addresses but can never spend your funds.
5. OBS, if you want the on-screen tip QR and alerts.

## Step 1: Install lovecash

Install [uv](https://docs.astral.sh/uv/) (a small tool that runs the
software), then in a terminal, from the lovecash folder:

```bash
uv sync --extra server
```

This downloads everything lovecash needs. You only do this once.

## Step 2: Connect your toy

1. Open the Lovense Connect app on your phone or desktop.
2. Turn on your toy and let the app connect to it.
3. Note the address and port. On desktop it's usually
`127.0.0.1` and port`30010`.

## Step 3: Run the setup wizard

**In your browser (easiest):** run

```bash
uv run lovecash serve
```

If there's no config yet, this starts a local setup wizard instead of
the relay — open http://localhost:8080/setup. It walks you through toy
detection, your wallet key (with a visual of the addresses it derives),
and safety limits, then writes `config.yaml` for you. Restart
`lovecash serve` afterwards to go live.

**Or in the terminal:**

```bash
uv run lovecash init
```

It asks for (same questions as the browser wizard):

- Your wallet's **xpub** (Master Public Key). In Electron Cash:
  Wallet -> Information -> Master Public Key. It starts with `xpub`.
  NEVER paste a private key (xprv) or seed phrase.
- A confirmation: the wizard shows your first receiving address and
  asks you to confirm it matches your wallet. This catches a
  wrong-wallet xpub before you go live. If it doesn't match, stop and
  re-run with the correct xpub.
- Your maximum toy strength (0-20) and duration per tip.
- Whether to enable the OBS overlay.

This writes `config.yaml`. Then run `uv run lovecash doctor` to verify
your xpub, your Electrum server, and your toy connection. You can
edit it later (see the [Tip Rules Guide](tip-rules.md)).

## Step 4: Check everything is connected

```bash
uv run lovecash doctor
```

You want three green checks:

- BCH xPub: valid
- Electrum server: reachable
- Lovense Connect: responding

If the Lovense check is yellow, your toy app isn't sharing the
connection yet. See [Troubleshooting](troubleshooting.md).

## Step 5: Test it safely BEFORE going live

This is important. Do this with the toy off your body the first time.

1. Set a low strength cap in`config.yaml` (`max_strength: 3`).
2. Run:

```bash
uv run lovecash run -v
```

3. Send yourself a tiny test tip from another wallet (a few cents).
4. Watch the toy react and the terminal show "Tip received".
5. Press Ctrl-C and confirm the toy stops immediately. This is your
   panic stop. Never trust the system until you've seen this work.

See the [Safety Guide](safety.md) for the full safe-testing routine.

## Step 6: Add the overlay to OBS

```bash
uv run lovecash serve
```

It prints a web address. Then in OBS:

1. Sources -> add -> Browser.
2. Paste the address (usually`http://localhost:8080/overlay`).
3. Set width 1920, height 1080.

You'll see a tip QR code in the corner and live tip alerts when money
comes in. Position and resize it however you like.

## Step 7: Go live

With`uv run lovecash serve` running and the overlay in OBS, you're
ready. Viewers scan the QR, send BCH, and your toy responds. Keep the
terminal window visible so you can hit Ctrl-C to stop instantly if
needed.

## Daily routine once set up

Each stream:

1. Connect your toy in the Lovense app and enable the PC connection.
2.`uv run lovecash serve`
3. Make sure the overlay shows "live" (green) in the corner.
4. Stream.

To stop: press Ctrl-C in the terminal. The toy stops and lovecash
shuts down cleanly.

## Where to go next

- Design your tip menu: [Tip Rules Guide](tip-rules.md)
- Stay safe: [Safety Guide](safety.md)
- Something broken? [Troubleshooting](troubleshooting.md)
