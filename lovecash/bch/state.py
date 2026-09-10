"""Persisted watcher state: which txids already fired the toy.

Without this, lovecash has amnesia across restarts and cannot tell a
tip that arrived while it was offline from one it already credited —
so it credits neither. The state file closes that gap.

Fail-safe contract: a missing, unreadable, or foreign state file means
"start fresh and assume everything on-chain was already handled" — the
watcher will miss offline tips before it ever risks firing the toy for
a stale one.
"""

import json
import logging
import os
from pathlib import Path

log = logging.getLogger("lovecash.state")

_VERSION = 1


def default_state_dir() -> Path:
    override = os.environ.get("LOVECASH_STATE_DIR")
    if override:
        return Path(override)
    return Path.home() / ".lovecash"


class StateStore:
    """Small JSON document beside the performer's other state.

    Keyed by xpub tail so two wallets never share a file. Writes are
    atomic (temp file + rename): a crash mid-write must never leave a
    half-written file that could cause double-fires on next start.
    """

    def __init__(self, path: Path, xpub_tail: str) -> None:
        self._path = path
        self._xpub_tail = xpub_tail
        self.seen: dict[str, None] = {}  # insertion-ordered FIFO
        self.pending_conf: dict[str, str] = {}  # txid -> scripthash
        self.pending_addrs: dict[str, int] = {}  # scripthash -> index

    def load(self) -> bool:
        """Populate from disk. Returns True only for a valid, current,
        same-wallet file; anything else is a fresh (fail-safe) start."""
        try:
            data = json.loads(self._path.read_text())
        except FileNotFoundError:
            return False
        except (OSError, ValueError) as exc:
            log.warning(
                "State file %s unreadable (%s) — starting fresh", self._path, exc
            )
            return False
        if data.get("version") != _VERSION or data.get("xpub_tail") != self._xpub_tail:
            log.warning(
                "State file %s is for a different wallet or version — starting fresh",
                self._path,
            )
            return False
        self.seen = dict.fromkeys(data.get("seen", []))
        self.pending_conf = dict(data.get("pending_conf", {}))
        self.pending_addrs = {
            str(k): int(v) for k, v in data.get("pending_addrs", {}).items()
        }
        log.info(
            "Loaded watcher state: %d seen, %d pending confirmation",
            len(self.seen),
            len(self.pending_conf),
        )
        return True

    def save(self) -> None:
        payload = {
            "version": _VERSION,
            "xpub_tail": self._xpub_tail,
            "seen": list(self.seen),
            "pending_conf": self.pending_conf,
            "pending_addrs": self.pending_addrs,
        }
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(payload))
            os.replace(tmp, self._path)
        except OSError as exc:
            # Losing state means missing offline tips later (safe
            # direction), never double-firing. Log and continue.
            log.error("Could not persist watcher state: %s", exc)
