import re
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from lovecash.models import TipRule, TokenRule


class Playback(StrEnum):
    OVERRIDE = "override"
    QUEUE = "queue"


class TrimStrategy(StrEnum):
    DROP_OLDEST = "drop_oldest"  # responsive: keep recent tips
    DROP_NEWEST = "drop_newest"  # reject the incoming tip's action
    COMPRESS = "compress"  # keep all, shrink durations to fit


class ToyConfig(BaseModel):
    toy_id: str  # Lovense device id
    max_strength: int | None = None  # falls back to global limits
    max_duration_s: float | None = None


class Limits(BaseModel):
    """Hard caps the performer sets. Enforced in the controller layer."""

    max_strength: int = Field(default=12, ge=0, le=20)
    max_duration_s: float = Field(default=30.0, ge=0, le=3600)
    min_seconds_between_commands: float = Field(default=0.5, ge=0)

    playback: Playback = Playback.QUEUE
    max_queue_seconds: float = Field(default=30.0, ge=0)
    trim_strategy: TrimStrategy = TrimStrategy.DROP_OLDEST
    # compress won't shrink a command below this, so nothing becomes a
    # meaningless flicker. Excess beyond what compression can absorb
    # falls back to dropping oldest.
    min_compressed_duration_s: float = Field(default=1.0, ge=0)

    def for_toy(self, toy: ToyConfig) -> Limits:
        return self.model_copy(
            update={
                "max_strength": toy.max_strength
                if toy.max_strength is not None
                else self.max_strength,
                "max_duration_s": toy.max_duration_s
                if toy.max_duration_s is not None
                else self.max_duration_s,
            }
        )


class LovenseConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 30010
    use_https: bool = True
    toys: list[ToyConfig] = []  # multi-toy; empty = legacy single
    toy_id: str | None = None  # legacy single-toy

    def resolved_toys(self) -> list[ToyConfig]:
        """Normalize legacy single-toy config into the toys list."""
        if self.toys:
            return self.toys
        # Legacy: one toy (named or the device's first).
        return [ToyConfig(toy_id=self.toy_id or "default")]


class ElectrumServer(BaseModel):
    host: str
    port: int = 50002
    ssl: bool = True
    # Verify the server's TLS certificate. On by default: without it a
    # network MITM can inject fake tips. Disable only for a server you
    # trust that uses a self-signed certificate.
    tls_verify: bool = True


class PricingConfig(BaseModel):
    enabled: bool = True
    always_confirm_above_usd: float = 500.0
    zeroconf_max_usd: float | None = None  # optional USD version of the floor
    max_staleness_seconds: float = 180.0
    refresh_seconds: float = 61.0
    verify_signature: bool = True


class BchConfig(BaseModel):
    xpub: str
    derivation_branch: int = 0
    gap_limit: int = 20
    rotate_on_payment: bool = True
    servers: list[ElectrumServer] = Field(
        default_factory=lambda: [
            ElectrumServer(host="fulcrum.jettscythe.xyz", port=50002, ssl=True),
            ElectrumServer(host="cashnode.bch.ninja", port=50002, ssl=True),
            ElectrumServer(host="blackie.c3-soft.com", port=50002, ssl=True),
        ]
    )
    zeroconf_max_sats: int = 100_000
    always_confirm_above_sats: int = 5_000_000
    heartbeat_seconds: float = 15.0
    reconnect_min_seconds: float = 1.0
    reconnect_max_seconds: float = 60.0
    dsproof_enabled: bool = True
    dsproof_window_seconds: float = 5.0
    pricing: PricingConfig = PricingConfig()

    @model_validator(mode="after")
    def _require_servers(self) -> BchConfig:
        if not self.servers:
            raise ValueError("bch.servers must contain at least one server")
        return self


class AlertConfig(BaseModel):
    """What the stream overlay shows and plays. Performer-configurable."""

    show_amount: bool = True
    show_memo: bool = True  # OP_RETURN memo text in alerts
    sound: bool = True
    min_sats: int = Field(default=0, ge=0)  # no alert pop below this
    goal_sats: int | None = None  # the goal amount itself
    show_goal: bool = True  # master switch: render the bar in the overlay
    accent: str = "#ff5c8a"  # overlay accent color


# Dust-scale covenant pots are pure griefing surface (serialized pot =>
# every pledge/refund blocks the next builder) and can't cover fees
# meaningfully. Constructor params are just redeem-script data, so this
# floor can only be enforced at config load — keep it in sync with the
# 5000-sat min pledge in goal_show.cash.
MIN_GOAL_SATS = 100_000


class GoalShowConfig(BaseModel):
    """Phase 3 covenant goal show. The pot address comes from
    contracts/address.mjs (token address, starts with r…). The watcher
    only observes the pot balance for the overlay goal bar — pledges are
    NOT tips and never trigger toys. See docs/covenant-goal-shows.md."""

    address: str  # covenant token-aware P2SH32 cashaddr
    goal_sats: int = Field(ge=MIN_GOAL_SATS)
    deadline: int = Field(ge=0)  # covenant deadline (block height/time)
    performer_pkh: str = ""  # 40-hex hash160 — enables auto-claim + client-side covenant rebuild
    # WalletConnect chain id for pairing. Default derived from the pot
    # address prefix; override for chipnet (wallets disagree on whether
    # chipnet is its own chain id or shares bchtest — verify on pairing).
    wc_chain: str | None = None

    @field_validator("performer_pkh")
    @classmethod
    def _check_pkh(cls, v: str) -> str:
        v = v.strip().lower()
        if v and not re.fullmatch(r"[0-9a-f]{40}", v):
            raise ValueError("performer_pkh must be 40 hex chars (hash160)")
        return v

    @property
    def resolved_wc_chain(self) -> str:
        if self.wc_chain:
            return self.wc_chain
        prefix = self.address.split(":", 1)[0].lower()
        return "bch:bitcoincash" if prefix == "bitcoincash" else "bch:bchtest"


class ServerConfig(BaseModel):
    enabled: bool = False
    bind_host: str = "127.0.0.1"
    bind_port: int = 8080
    # Shared secret the performer uses to authenticate control routes.
    # Required when binding to a non-loopback address (enforced at startup).
    relay_token: str | None = None
    alerts: AlertConfig = AlertConfig()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOVECASH_", env_nested_delimiter="__")

    limits: Limits = Limits()
    lovense: LovenseConfig = LovenseConfig()
    bch: BchConfig
    server: ServerConfig = ServerConfig()
    rules: list[TipRule] = []
    token_rules: list[TokenRule] = []  # CashToken tips (CHIP-2022-02)
    goal_show: GoalShowConfig | None = None  # Phase 3 covenant pot

    @classmethod
    def from_yaml(cls, path: str | Path) -> Settings:
        data = yaml.safe_load(Path(path).read_text()) or {}
        return cls.model_validate(data)

    def save_yaml(self, path: str | Path) -> None:
        """Persist current settings. Note: a plain dump — template
        comments are not preserved."""
        p = Path(path)
        p.write_text(yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False))
        p.chmod(0o600)  # xpub reveals address history — owner-only
