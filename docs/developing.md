# Developer Guide

## Setup

```bash
uv sync --extra server --group dev
```

## Project layout

| Path | Responsibility |
|---|---|
| lovecash/models.py | Pydantic models: TipEvent, ToyCommand, TipRule |
| lovecash/config.py | Settings, limits, playback, trim strategy |
| lovecash/safety.py | Panic stop and rate-limit gate |
| lovecash/bch/ | CashAddr decode, BIP21/QR, Electrum client, watcher |
| lovecash/engine/ | Tip-to-command rule resolution |
| lovecash/lovense/ | Local Lovense Connect controller |
| lovecash/core/ | Orchestrator and command player (queue/override) |
| lovecash/server/ | FastAPI relay, OBS overlay, broadcast hub |
| lovecash/cli.py | Typer CLI: init, doctor, run, serve, qr |

## Architecture

A tip flows: watcher detects payment -> orchestrator -> rules engine
resolves a command -> command player (queues or overrides) -> controller
clamps to limits and checks the safety gate -> Lovense API.

The safety gate sits between every command and the hardware. Nothing in
the payment path can clear a panic stop.

## Running tests

```bash
uv run python -m compileall lovecash tests   # catch syntax issues
uv run --extra server pytest -v
```

Live-network tests are opt-in:

```bash
uv run pytest -m integration
```

## Tip: catching paste/copy errors

After editing, always compile-check before testing. A flattened nested
block parses as valid-but-wrong code that tests catch late:

```bash
uv run python -m compileall <file>
uv run python -c "import <module>"
```

## Coverage

Logic and safety layers should stay well-covered. Network plumbing
(electrum.py, watcher.py) needs a live node and is covered by opt-in
integration tests rather than mocks.

## Known areas for improvement

- The Electrum client has no automatic reconnection.
- Single toy and single performer only.
- Compression can't shorten a command already running on the toy.
