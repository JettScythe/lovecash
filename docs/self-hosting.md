# Self-Hosting Guide

This is for running the relay on a server you control, e.g. so OBS can
reach it remotely or so it runs continuously. It's more technical than
the performer guide. If you just want to stream from one computer, you
don't need this — `uv run lovecash serve` is enough.

## What the relay does

The relay serves the OBS overlay (tip QR + live alerts) and exposes
control endpoints. It does not hold funds or keys. It's a convenience
layer over the same core that `run` uses.

## Running with Docker

```bash
docker compose up --build
```

This builds the image and starts the relay on port 8080, reading your
`config.yaml`.

## Exposing it publicly: required precautions

The relay refuses to start on a public address without a relay token,
because the `/resume` endpoint could otherwise be used by anyone to clear
your panic stop. To expose it:

1. Set a long, random token in `config.yaml`:

```yaml
server:
  bind_host: 0.0.0.0
  bind_port: 8080
  relay_token: <a-long-random-secret-string>
```

2. Put it behind HTTPS (a reverse proxy like Caddy or nginx with TLS).
   Never expose the control endpoints over plain HTTP on the internet.

3. Control endpoints (`/panic`,`/resume`) require the token in the
`X-Relay-Token` header. The overlay and QR endpoints are read-only and
   safe to expose (they only show a public receiving address).

## Endpoint reference

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| /tip | GET | none | Public viewer tip page (QR + goal-show pledges) |
| /overlay | GET | none | OBS browser source page |
| /overlay-ws | WS | none | Live tip events |
| /qr.png?amount= | GET | none | Tip QR image |
| /qr.svg | GET | none | Vector tip QR |
| /uri?amount= | GET | none | BIP21 URI as JSON |
| /api/status | GET | none | Public status (receive address, goal pot) |
| /api/goal_pot | GET | none | Goal-show pot state (read-only Electrum proxy) |
| /api/utxos?address= | GET | none | Address UTXO lookup (read-only Electrum proxy) |
| /api/token_meta?category= | GET | none | Token name/symbol lookup (read-only BCMR proxy) |
| /dashboard | GET | none* | Performer dashboard page — *controls still need the token |
| /api/settings | GET/POST | token | Live settings read/save |
| /panic | POST | token | Stop and block all commands |
| /resume | POST | token | Clear the panic stop |
| /health | GET | none | Liveness and stop state |

Viewer-facing tip page: link your audience to `https://your-domain/tip`.
HTTPS is effectively required for goal-show pledges — wallet pairing and
clipboard copy need a secure context. A tunnel (Tailscale Funnel,
Cloudflare Tunnel) in front of the loopback relay works too, no domain or
router changes needed.

Rate-limit `/api/utxos` and `/api/goal_pot` at the proxy on a public
relay: each request fans out to Electrum, and on servers without the
Fulcrum `include_tokens` extension one `/api/utxos` call fetches every
UTXO's full raw transaction — an amplification vector if left open.

## Environment variable overrides

Any config value can be overridden by an environment variable, useful in
containers. Nested keys use double underscores:

```bash
LOVECASH_BCH__XPUB=xpub...
LOVECASH_SERVER__RELAY_TOKEN=your-secret
```

## Important limitation

The relay assumes a single performer. It is not a
multi-tenant service. Each performer should run their own instance with
their own config and their own wallet xPub.
