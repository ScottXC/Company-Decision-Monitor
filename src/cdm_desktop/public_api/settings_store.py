from __future__ import annotations

import json
from typing import Any

from cdm_desktop.paths import AppPaths, get_app_paths
from cdm_desktop.public_api.web_evidence_models import CrawlPolicy


class PublicApiSettingsStore:
    def __init__(self, paths: AppPaths | None = None) -> None:
        self.paths = paths or get_app_paths()
        self.path = self.paths.app_data_dir / "public_api_settings.json"

    def advanced_api_providers_enabled(self) -> bool:
        return bool(self._read().get("advanced_api_providers_enabled", False))

    def set_advanced_api_providers_enabled(self, enabled: bool) -> None:
        data = self._read()
        data["advanced_api_providers_enabled"] = bool(enabled)
        self._write(data)

    def crawlergo_path(self) -> str:
        return str(self._read().get("crawlergo_path") or "")

    def set_crawlergo_path(self, path: str) -> None:
        data = self._read()
        data["crawlergo_path"] = path.strip()
        self._write(data)

    def crawlergo_policy(self) -> CrawlPolicy:
        data = self._read()
        return CrawlPolicy(
            respect_robots=True,
            max_pages_per_domain=_int(data.get("crawlergo_max_pages"), 10, 1, 50),
            max_depth=_int(data.get("crawlergo_max_depth"), 1, 0, 3),
            request_delay_seconds=float(_int(data.get("crawlergo_request_delay_seconds"), 1, 1, 30)),
            timeout_seconds=_int(data.get("crawlergo_timeout_seconds"), 15, 5, 120),
            allow_full_text_display=bool(data.get("crawlergo_allow_full_text_display", False)),
            cache_ttl_seconds=_int(data.get("crawlergo_cache_ttl_seconds"), 86400, 3600, 604800),
        )

    def set_crawlergo_policy(self, policy: CrawlPolicy) -> None:
        data = self._read()
        data["crawlergo_max_pages"] = int(policy.max_pages_per_domain)
        data["crawlergo_max_depth"] = int(policy.max_depth)
        data["crawlergo_request_delay_seconds"] = int(policy.request_delay_seconds)
        data["crawlergo_timeout_seconds"] = int(policy.timeout_seconds)
        data["crawlergo_allow_full_text_display"] = bool(policy.allow_full_text_display)
        data["crawlergo_cache_ttl_seconds"] = int(policy.cache_ttl_seconds)
        self._write(data)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _write(self, data: dict[str, Any]) -> None:
        self.paths.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))
