## v0.7.0 (2026-06-04)

### Feat

- **bch**: DSProof-aware 0-conf — credit mid-range tips after a short
  double-spend verification window instead of waiting for a block.
  Validated end-to-end against live network double-spends. On by default.
- **bch**: high-value confirmation ceiling (`always_confirm_above_sats`) —
  tips above the ceiling always wait for a confirmation, since DSProof
  alone is insufficient at high value.

### BREAKING

- **rules**: removed per-rule `min_confirmations`. Confirmation behavior
  is now governed globally by the `bch` value tiers above.

## v0.6.0 (2026-06-04)

### Feat

- **.**: add queue overlay & runaway scans

### Refactor

- **.**: bump uv.lovk lovecash version, remove unused ADDR

## v0.5.0 (2026-06-03)

### BREAKING CHANGE

- xPub *only*

### Fix

- **.**: remove single address support
- **cli.py**: await anyio.Path.writexxxx

### Refactor

- **.**: correct type hints

## v0.4.1 (2026-06-02)

### Fix

- **payment**: initialize 'advanced' before scan look (block notifications crashed)

## v0.4.0 (2026-06-02)

### Feat

- **bch**: xpub watch-only mode with rotating per-tip addresses

## v0.3.0 (2026-06-02)

### Feat

- **bch**: electrum auto-reconnect, heartbeat, gap recovery, status surfacing
- **core**: pluggable TriggerSource abstraction

## v0.2.0 (2026-06-01)

### Feat

- **initial-working-release**: BCH tips trigger Lovense toys with queue playback, OBS overlay, configurable trim strategy, and a panic-stop safety layer
