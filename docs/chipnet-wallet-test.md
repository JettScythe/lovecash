# Chipnet wallet test runbook (goal-show pledging, Cashonize)

One-time manual gate before viewers use pledge mode. Everything runs on
chipnet (play money). The covenant pot is live and seeded (10,000 sats,
goal 50,000, deadline ~2 months out).

## Setup (already running)

- `uv run lovecash serve -c config.chipnet-test.yaml` — relay on
  http://127.0.0.1:8080, watching the pot at
  `bchtest:rvud5m27y2x2hfchame90qu9n9phu2nphuyxsec2gj00u73us2ur2fppezgql`
  (contract params: performerPkh `3b3c1129…53c7`, goal 50,000,
  deadline 422,981).
- The throwaway performer key lives in `contracts/.chipnet-wif`
  (gitignored). Cashonize gets its OWN fresh wallet — do not import this
  key there; the point is testing the viewer side.

## Test steps

0. Hard-refresh http://127.0.0.1:8080/tip (Cmd-Shift-R) — the panel is
   static HTML cached by the browser; the wallet bundle loads fresh.
   chipnet.imaginary.cash's EXPLORER is flaky (502s); its Electrum
   server is fine. To verify any txid, ask lovecash (it reads the chain
   directly) rather than the explorer.
1. Open Cashonize (v0.9.0+; on macOS use the web app at cashonize.com).
   Create a new wallet. If Cashonize has a chipnet/testnet toggle, use
   it; if not, **stop** — mainnet Cashonize must never touch this test
   (report back, we'll fund a tiny mainnet pot instead).
2. Get the wallet some chipnet coins: https://tbch.googol.cash (captcha
   is a simple sum; chain = chipnet).
3. Open http://127.0.0.1:8080/tip — the goal-show panel should show the
   seeded pot progress (10,000 / 50,000 sats) once the seed confirms.
4. Click **Connect wallet** → a pairing QR appears. In Cashonize:
   dApps/WalletConnect area → WizardConnect → scan (or paste the URI
   under the QR).
5. Enter 5,000 sats, pledge. Cashonize should show a signing prompt.
   Approve.
6. Watch the /tip panel and the overlay (http://127.0.0.1:8080/overlay):
   the bar should jump to 15,000. The receipt NFT (category
   `4b0fc714…f4e1`) should appear in Cashonize's token list.

## What to report

- Pairing: did the QR scan/paste work, any namespace or method errors?
- Signing prompt: does Cashonize render the covenant spend sanely (it
  receives no contract metadata — expected plain-script display)?
- Did the wallet broadcast, or sign-only? (Check the explorer link the
  page shows; if nothing lands, that's the broadcast-semantics finding.)
- Receipt NFT visible with the right category?
- Any console errors (browser devtools console output).

## After the test

The leftover pot is refundable/sweepable with the throwaway key via a
re-run of `contracts/chipnet_e2e.mjs` helpers. Chipnet coins are
worthless; nothing to secure.
