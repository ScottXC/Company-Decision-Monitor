from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cdm_desktop.paths import AppPaths, get_app_paths

SENSITIVE_HINTS = ("key", "token", "secret", "guid", "apikey", "api_token")


def sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in params.items():
        lowered = key.lower()
        if any(hint in lowered for hint in SENSITIVE_HINTS):
            sanitized[key] = "***"
        else:
            sanitized[key] = value
    return sanitized


def cache_key(provider: str, endpoint: str, params: dict[str, Any], query: str = "") -> str:
    payload = {
        "provider": provider,
        "endpoint": endpoint,
        "params": sanitize_params(params),
        "query": _normalize_key_text(query),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ApiCache:
    def __init__(self, paths: AppPaths | None = None, ttl_seconds: int = 900) -> None:
        self.paths = paths or get_app_paths()
        self.ttl_seconds = ttl_seconds
        self.cache_dir = self.paths.cache_dir / "public_api"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> Any | None:
        payload = self._read_payload(key)
        if payload is None:
            return None
        expires_at = payload["expires_at"]
        if expires_at < _now():
            return None
        return payload["data"]

    def get_stale(self, key: str) -> Any | None:
        payload = self._read_payload(key)
        if payload is None:
            return None
        return payload["data"]

    def _read_payload(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            expires_at = _parse_datetime(str(payload["expires_at"]))
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            return None
        return {"expires_at": expires_at, "data": payload.get("data")}

    def set(self, key: str, data: Any, ttl_seconds: int | None = None) -> None:
        expires_at = _now() + timedelta(seconds=ttl_seconds or self.ttl_seconds)
        payload = {"expires_at": expires_at.isoformat(), "data": data}
        self._path(key).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def clear(self) -> int:
        count = 0
        for path in self.cache_dir.glob("*.json"):
            try:
                path.unlink()
                count += 1
            except OSError:
                continue
        return count

    def size_bytes(self) -> int:
        return sum(path.stat().st_size for path in self.cache_dir.glob("*.json") if path.is_file())

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"


def _normalize_key_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").strip().casefold()
    return re.sub(r"\s+", " ", normalized)


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
