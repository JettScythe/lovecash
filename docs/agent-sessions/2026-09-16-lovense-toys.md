# Session log: Lovense toy support expansion

- Date: 2026-09-16
- Base branch: main
- Working branch: agent/lovense-toys
- Model: k3 (main agent, no subagents)

## Goal

Support as many Lovense toys as possible in the KNOWN_TOYS table, using
official Lovense documentation for the action list and strength ranges.

## Files changed

- `lovecash/models.py` — added `Action.OSCILLATE/FINGERING/SUCTION`;
  added `ACTION_MAX_STRENGTH` + `action_max_strength()` (Pump/Depth are
  hardware-limited to 0-3 per the official Standard API docs).
- `lovecash/lovense/toys.py` — KNOWN_TOYS expanded from 2 entries to 41
  (Lush/Hush/Domi/Ambi/Edge/Diamo/Gush/Calor/Dolce/Ferri/Hyphy/Exomoon/
  Gemini/Lapis/Mission lines, Nora, Ridge, Gravity, Vulse, Max/Max 2,
  Osci line, Flexer, Tenera line). New categories OSCILLATOR, FINGERING,
  SUCTION with rule ladders. PUMP ladder fixed to 1/2/3 (was 3/8/14,
  above the 0-3 hardware ceiling).
- `lovecash/lovense/controller.py` — `_clamp` now also clamps to the
  action's hardware ceiling (fixes silent no-op rules on Pump toys).
- `lovecash/cli.py`, `lovecash/server/ui/setup.py`,
  `lovecash/server/ui/dashboard.py` — action pickers list the three new
  actions.
- `tests/test_toys.py` — new: every KNOWN_TOYS entry round-trips through
  toy_defaults/build_rules and stays within the hardware ceiling;
  controller pump-clamp checks; case-insensitive action parsing.

### Stroke support (follow-up in same session)

- `lovecash/models.py` — `stroke_min`/`stroke_max` (0-100) on ToyCommand,
  TipRule, TokenRule + shared `_validate_stroke`: both-or-neither,
  min < max, span >= 20 (Lovense silently ignores smaller spans),
  Thrusting-only.
- `lovecash/lovense/controller.py` — `_action_string` emits
  `Stroke:min-max,Thrusting:n` when a stroke range is set.
- `lovecash/server/ui/dashboard.py` — stroke min/max inputs on tip and
  token rule rows (the editor rebuilds rules on save, so without inputs
  it would have dropped the fields) + client-side validation.
- `lovecash/config.template.yaml` — documents the action list and the
  optional stroke fields.

### All action (follow-up in same session)

- `Action.ALL = "All"` — drives every channel of a multi-function toy at
  once (Nora vibrate+rotate, Max 2 vibrate+pump). Wire format is plain
  `All:n`, so no controller changes beyond the enum. Added to the CLI
  prompt, setup wizard and dashboard action lists, and the template
  comment.

### Full Standard API surface (user request: "ALL lovense capability")

- `lovecash/models.py` — restructured around a shared `CommandFields`
  base (ToyCommand/TipRule/TokenRule inherit it): `extra_actions`
  (multi-channel `Vibrate:5,Rotate:10`), `stop_previous`, loop fields,
  `preset` (pulse/wave/fireworks/earthquake), `pattern` +
  `pattern_interval_ms`, `positions` (PatternV2 InitPlay keyframes).
  Validators reject the Lovense silent-failure shapes: duplicate
  channels, All/Stop as a channel, mode conflicts, stroke/loop outside
  Function mode, pattern >50 steps or out of 0-20, non-increasing
  position timestamps.
- `lovecash/lovense/controller.py` — `_payload()` builds Preset /
  PatternV2 InitPlay / Pattern (apiVer 2, comma-separated feature
  letters) / Function payloads; per-channel clamping in `_clamp`;
  `set_position()` (Solace Pro real-time Position command);
  `stop_all` now sends PatternV2 Stop BEFORE Function Stop — a running
  position pattern does not answer to Function:Stop, and the panic
  invariant must halt everything.
- `lovecash/server/ui/dashboard.py` — rule rows stash the original rule
  (`row._raw`) and spread it on save, so config.yaml-authored advanced
  fields survive the dashboard editor (which only renders the common
  fields). No new UI for the advanced modes — config.yaml is the
  authoring surface.
- `tests/test_command_modes.py` — new, 23 tests over every mode's wire
  payload, clamping, and validation rejects.
- Whole-repo `ruff format` per user request (8 pre-existing drifted
  files reformatted); embedded dashboard/setup JS syntax-checked with
  dockerized `node --check`.

### WalletConnect reference removal (user request)

- No WalletConnect code/deps/URIs existed — references were comment/docs
  only. Scrubbed: `contracts/web/pledge_tx.test.mjs`, `contracts/README.md`,
  `docs/chipnet-wallet-test.md`, `docs/covenant-goal-shows.md`,
  `lovecash/server/ui/tip.py` (stale comment: bundle keyed on a
  WalletConnect project id — it never did; it's WizardConnect/Nostr),
  `lovecash/server/app.py` (/qr-data.png docstring).
- Left alone: `docs/agent-sessions/2026-09-10-goal-show-covenant.md` —
  a dated historical log, not living documentation.

### Pre-PR polish (user review pass)

- `config.example.yaml` — added a commented Solace stroke example + a
  pointer to the template's advanced-fields block.
- Dual-channel toys (Nora, Ridge, Max, Max 2, Osci 3, Gravity) now
  onboard with action `All` instead of their distinctive channel only —
  user decision; a single-channel default silently wasted half the toy.
  ToyCategory.ROTATOR/PUMP ladders remain for manual action picks but no
  KNOWN_TOYS entry uses them now.

### Dashboard rule-mode UI (user request)

- `lovecash/server/ui/dashboard.py` — rule rows gained a mode selector
  (Function / Preset / Pattern / Positions) with a `.rule-adv` sub-row:
  stroke range, replace-prev (stopPrevious), loop on/off, an
  extra-channels editor (add/remove channel+strength pairs), preset
  picker, pattern steps + interval, and ts:pos keyframe entry. Field
  collection switched from positional input indices (fragile) to class
  selectors; the `_raw` passthrough was dropped — every field is now
  editable, nothing to preserve. Client-side validation mirrors the
  server rules; server revalidates regardless.
- `lovecash/models.py` — `action`/`strength` got defaults so Preset and
  Positions rules don't carry dead fields.
- `tests/test_server.py` — round-trip test posting exactly what the new
  UI emits (multi-channel + preset + positions rules) through
  /api/settings, plus a mode-conflict 422 test.
- Embedded JS re-checked with dockerized `node --check`; fixed a `\s`
  regex escape that SyntaxWarned inside the non-raw HTML string.

### Tracking issue

- Opened https://github.com/JettScythe/lovecash/issues/20 for the
  Socket API transport + toy-event triggers + PatternV2 SyncTime — the
  one Lovense capability area deliberately not in this branch.

### Dashboard UX redesign (user feedback: "unintuitive as fuck")

- `lovecash/server/ui/dashboard.py` — rule rows replaced by
  plain-language cards: "When a tip is between [1000] and [10000] sats →
  run [Function ▾] [Vibrate ▾] at strength [slider] for [5] seconds on
  [toy]". Strength is a slider with live readout; presets are pill
  buttons; mode-specific hint lines; a live human-readable summary strip
  ("1000–9999 sats → Vibrate at 12 + Rotate at 6 for 8s") updates on
  every edit; stroke/loop/stop-previous/extra channels moved into a
  collapsed "Advanced options" <details>. Collect logic unchanged
  (class-based). Smoke-checked: /dashboard serves 200 with the new
  markup; JS node --check OK.

## Commands run

- `uv run python -m compileall lovecash tests`
- `uv run ruff check .` (+ `--fix`, `ruff format`)
- `uv run mypy`
- `uv run --extra server pytest -v`

## Outcome

- Tests: pass (218 passed; +23 in tests/test_command_modes.py, +14 in
  tests/test_toys.py, +2 in tests/test_server.py)
- Lint: pass (`ruff check` clean; `ruff format --check` clean — whole
  repo reformatted per user request, 8 pre-existing files included)
- Build: pass (compileall); embedded UI JS: `node --check` OK (docker)

## Notes

- Docstring invariant relaxed: the table previously demanded
  hardware-confirmed entries only. Entries are now sourced from Lovense's
  published action list + product lineup (user request: "as many as
  possible"); the docstring notes hardware confirmation is still welcome
  and unknown toys still fall back to asking in `init`.
- Assumption: GetToys name keys are the lowercase marketing name
  ("lush 3", "max 2", "tenera 2"), matching the two previously
  hardware-confirmed entries ("solace", "solace pro").
- Stroke + All + the full Standard API command surface implemented per
  user request (see sections above). The Socket API / toy-event triggers
  / PatternV2 SyncTime are tracked in issue #20 instead of this branch.
- Skipped: Lovense Mini Sex Machine / Spinel — GetToys name strings not
  confidently known; add on hardware confirmation.
- Not committed: user did not request a commit.
