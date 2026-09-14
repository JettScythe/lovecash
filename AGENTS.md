# AGENTS.md

Performer-first bridge: BCH tips (Electrum/Fulcrum watcher) -> rules engine -> Lovense Connect local API, plus a FastAPI relay serving an OBS overlay. Python package in `lovecash/`, tests in `tests/`, plus a separate JS/CashScript covenant subproject in `contracts/`.

## Setup & commands

- Python 3.14, managed by `uv`. Full dev env: `uv sync --extra server --group dev`.
- The `server` extra is required to run the test suite (server tests import fastapi).
- Verification, in CI order (`.github/workflows/ci.yaml`):
  1. `uv run python -m compileall lovecash tests`
  2. `uv run ruff check .`
  3. `uv run mypy`
  4. `uv run --extra server pytest -v`
- Single test: `uv run --extra server pytest tests/test_rules.py -v`
- Default pytest run excludes live-network tests (`addopts = -m 'not integration'`). `uv run pytest -m integration` needs a real Electrum/Fulcrum server.
- Pre-commit runs `ruff --fix` + `ruff-format`, and validates commit messages with commitizen (Conventional Commits are enforced, not just preferred). pytest runs at pre-push.

## Conventions & quirks

- Ruff per-file ignores in `pyproject.toml` are deliberate: `assert` in `electrum.py` and tests, `0.0.0.0` bind in `cli.py`, self-signed-cert verify-off for the local Lovense Connect API (`onboard.py`, `controller.py`). Don't "fix" these.
- mypy is intentionally lenient (`strict = false`); keep `warn_unused_ignores` clean.
- Tests autouse a fixture that sets `LOVECASH_STATE_DIR` to `tmp_path` — never let tests touch the real `~/.lovecash` state.
- `config.yaml` is gitignored and holds a real xPub. `config.example.yaml` is the reference; `lovecash/config.template.yaml` is force-included in the wheel (excluded from pre-commit check-yaml).
- `gp-oracle` is pinned to a git rev in `[tool.uv.sources]` — bumping it means updating the rev and `uv.lock`.

## Safety invariants (do not weaken)

- `limits` (max_strength, max_duration_s, rate limit) are enforced in the controller, below the rules layer. Rules can never exceed them.
- The panic stop sits between every command and the hardware; nothing in the payment path may clear it.
- The relay must refuse to bind non-loopback without `server.relay_token`.

## contracts/ subproject (CashScript covenant)

- Separate Node/npm project; node_modules and artifacts are gitignored. Compile/test via dockerized node — exact commands in `contracts/README.md`.
- After any contract change: rebuild the web bundle (`npm run build-web`, docker) and copy `contracts/web-dist/pledge.bundle.js` to `lovecash/server/ui/static/pledge.bundle.js` — the served bundle is a checked-in copy.
- Never split covenant deploy into mint-then-seed (forge-receipt gap); genesis must seed directly. See `contracts/README.md`.

## Docs

`docs/developing.md` has the module-by-module layout table and architecture flow. Note its "known areas for improvement" list is stale (multi-toy and reconnection have since been implemented) — trust the code over that section.
