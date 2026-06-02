# Frequently Asked Questions

## Does lovecash take a cut of my tips?

No. The software itself takes nothing. Tips go directly from the viewer's
wallet to your wallet. There is no middleman in the payment.

## Can lovecash access my money or wallet?

No. You give it only your public receiving address — the same thing you'd
paste anywhere to get paid. It never has your password, seed phrase, or
private keys, and it cannot move funds.

## Why Bitcoin Cash instead of credit cards or other crypto?

- Fees are tiny (a fraction of a cent), so small tips make sense.
- Payments are final — no chargebacks, which is a common problem on
  card-based platforms.
- It's fast enough to feel responsive.

## Do viewers need anything special?

Just a Bitcoin Cash wallet app on their phone. They scan the QR code on
your stream and send a tip. Most BCH wallets can scan and prefill the
amount automatically.

## Can I use this alongside Lovense Stream Master?

Not at the same time. A toy can only be controlled by one app at once.
Use the Lovense Connect app with lovecash, or use Stream Master — not
both in the same session.

## What if someone sends a tip that doesn't match any rule?

Nothing happens to the toy, but you still receive the money. It's a good
idea to have a low-cost lowest tier so small tips still do something.

## Can I change my tip menu mid-stream?

You edit `config.yaml` and restart lovecash to load changes. Plan your
menu before going live for the smoothest experience.

## Is this legal?

Running an adult-content service involves real legal obligations that
vary by location — age verification, record-keeping, and money rules.
lovecash is designed to be non-custodial (it never holds your money),
which helps, but this is not legal advice. Consult a qualified
professional before operating commercially.

## Can I run this without OBS?

Yes. Use `uv run lovecash run` instead of `serve`. You won't get the
on-screen QR and alerts, but the toy still responds to tips. You'd share
your tipping address with viewers another way.

## What happens if my internet drops mid-stream?

Tip detection pauses until the connection returns. If tips stop
triggering, restart lovecash. Improved automatic reconnection is planned.

## Can I use multiple toys?

Currently lovecash controls one toy at a time (the first one detected, or
the one set as `toy_id` in your config).
