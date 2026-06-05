## v0.7.0 (2026-06-04)

### Feat

- **bch**: DSP-aware 0-conf - safe credit for high value tips
- **bch**: add DSProofs (untested

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
