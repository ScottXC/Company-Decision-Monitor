from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from cdm_desktop.public_api.models import ProviderError, ProviderStatus


@dataclass
class ProviderHealth:
    provider_id: str
    provider_name: str
    status: str = "unknown"
    configured: bool = True
    last_checked_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error_type: str = ""
    last_error_message: str = ""
    consecutive_failures: int = 0
    disabled_until: datetime | None = None
    average_latency_ms: int = 0

    def in_backoff(self, now: datetime | None = None) -> bool:
        now = now or utc_now()
        return self.disabled_until is not None and self.disabled_until > now


class ProviderHealthTracker:
    def __init__(self, *, failure_threshold: int = 3, backoff_seconds: int = 90) -> None:
        self.failure_threshold = failure_threshold
        self.backoff_seconds = backoff_seconds
        self._items: dict[str, ProviderHealth] = {}

    def get(self, provider_id: str, provider_name: str = "") -> ProviderHealth:
        if provider_id not in self._items:
            self._items[provider_id] = ProviderHealth(provider_id, provider_name or provider_id)
        return self._items[provider_id]

    def should_skip(self, provider_id: str, provider_name: str = "", *, manual: bool = False) -> ProviderStatus | None:
        if manual:
            return None
        health = self.get(provider_id, provider_name)
        if not health.in_backoff():
            return None
        until = health.disabled_until.isoformat(timespec="seconds") if health.disabled_until else ""
        return ProviderStatus(
            provider_id,
            provider_name or health.provider_name,
            "fallback",
            "provider_unavailable",
            f"该数据源连续失败，已短暂暂停自动请求；手动测试连接不受影响。恢复时间：{until}",
            last_error=health.last_error_message,
        )

    def record_success(self, provider_id: str, provider_name: str = "", *, latency_ms: int = 0) -> ProviderHealth:
        health = self.get(provider_id, provider_name)
        now = utc_now()
        health.status = "enabled"
        health.last_checked_at = now
        health.last_success_at = now
        health.consecutive_failures = 0
        health.disabled_until = None
        if latency_ms:
            health.average_latency_ms = (
                latency_ms if not health.average_latency_ms else int((health.average_latency_ms + latency_ms) / 2)
            )
        return health

    def record_error(
        self,
        provider_id: str,
        provider_name: str,
        error: ProviderError,
        *,
        configured: bool = True,
    ) -> ProviderHealth:
        health = self.get(provider_id, provider_name)
        now = utc_now()
        health.status = error.state
        health.configured = configured
        health.last_checked_at = now
        health.last_error_at = now
        health.last_error_type = error.state
        health.last_error_message = error.message
        if error.state in {"not_configured", "empty"}:
            health.consecutive_failures = 0
        else:
            health.consecutive_failures += 1
        if health.consecutive_failures >= self.failure_threshold and error.retryable:
            health.disabled_until = now + timedelta(seconds=self.backoff_seconds)
        return health


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_timestamp() -> str:
    return utc_now().isoformat(timespec="seconds").replace("+00:00", "Z")
