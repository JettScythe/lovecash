from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from lovecash.models import TipRule


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

    def for_toy(self, toy: ToyConfig) -> "Limits":
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


class BchConfig(BaseModel):
    xpub: str
    derivation_branch: int = 0
    gap_limit: int = 20
    rotate_on_payment: bool = True
    electrum_host: str = "fulcrum.jettscythe.xyz"
    electrum_port: int = 50002
    electrum_ssl: bool = True
    servers: list[ElectrumServer] = []  # optional failover pool
    zeroconf_max_sats: int = 100_000
    always_confirm_above_sats: int = 5_000_000
    heartbeat_seconds: float = 15.0
    reconnect_min_seconds: float = 1.0
    reconnect_max_seconds: float = 60.0
    dsproof_enabled: bool = True
    dsproof_window_seconds: float = 5.0

    def server_pool(self) -> list[ElectrumServer]:
        primary = ElectrumServer(
            host=self.electrum_host,
            port=self.electrum_port,
            ssl=self.electrum_ssl,
        )
        return [primary, *self.servers]


class ServerConfig(BaseModel):
    enabled: bool = False
    bind_host: str = "127.0.0.1"
    bind_port: int = 8080
    # Shared secret the performer uses to authenticate control routes.
    # Required when binding to a non-loopback address (enforced at startup).
    relay_token: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOVECASH_", env_nested_delimiter="__")

    limits: Limits = Limits()
    lovense: LovenseConfig = LovenseConfig()
    bch: BchConfig
    server: ServerConfig = ServerConfig()
    rules: list[TipRule] = []

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Settings":
        data = yaml.safe_load(Path(path).read_text()) or {}
        return cls.model_validate(data)
