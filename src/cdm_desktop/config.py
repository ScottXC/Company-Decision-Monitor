from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CDM_", extra="ignore")

    http_timeout_seconds: int = Field(default=15, ge=1, le=120)
    max_fetch_bytes: int = Field(default=5_000_000, ge=10_000, le=50_000_000)
    monitoring_interval_minutes: int = Field(default=60, ge=1, le=1440)
    monitoring_enabled: bool = False
    run_on_startup: bool = False
    alert_threshold_confidence: int = Field(default=60, ge=0, le=100)
    alert_threshold_materiality: int = Field(default=40, ge=0, le=100)


def load_config() -> AppConfig:
    return AppConfig()
