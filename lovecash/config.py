from __future__ import annotations

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


class LovenseConfig(BaseModel):
    # Lovense Connect / Game Mode local API endpoint.
    host: str = "127.0.0.1"
    port: int = 30010
    use_https: bool = True
    # If empty, the first reported toy is used.
    toy_id: str | None = None


class BchConfig(BaseModel):
    # The performer's own receiving address. Never a key, never custody.
    address: str
    # A public Fulcrum/ElectrumX server, or the performer's own.
    electrum_host: str = "fulcrum.fountainhead.cash"
    electrum_port: int = 50002
    electrum_ssl: bool = True
    # Fire on 0-conf below this sats threshold; require 1+ conf above it.
    zeroconf_max_sats: int = 100_000


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
    def from_yaml(cls, path: str | Path) -> Settings:
        data = yaml.safe_load(Path(path).read_text()) or {}
        return cls.model_validate(data)
