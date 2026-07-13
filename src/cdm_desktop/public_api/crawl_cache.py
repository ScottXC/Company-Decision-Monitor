from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cdm_desktop.paths import AppPaths, get_app_paths
from cdm_desktop.public_api.web_evidence_models import WebEvidenceItem


def url_cache_key(url: str) -> str:
    return hashlib.sha256((url or "").strip().encode("utf-8")).hexdigest()


class WebEvidenceCache:
    def __init__(self, paths: AppPaths | None = None, ttl_seconds: int = 86400) -> None:
        self.paths = paths or get_app_paths()
        self.ttl_seconds = ttl_seconds
        self.cache_dir = self.paths.cache_dir / "web_evidence"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, url: str) -> WebEvidenceItem | None:
        payload = self._read(url)
        if payload is None:
            return None
        if payload["expires_at"] < _now():
            return None
        item = WebEvidenceItem.from_dict(payload["data"])
        item.from_cache = True
        return item

    def set(self, item: WebEvidenceItem, ttl_seconds: int | None = None) -> None:
        data = item.to_dict()
        data.pop("raw_html", None)
        data["extracted_text_preview"] = (data.get("extracted_text_preview") or "")[:800]
        data["content_snippet"] = (data.get("content_snippet") or "")[:300]
        payload = {
            "expires_at": (_now() + timedelta(seconds=ttl_seconds or self.ttl_seconds)).isoformat(),
            "data": data,
        }
        self._path(item.final_url or item.source_url).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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

    def _read(self, url: str) -> dict[str, Any] | None:
        path = self._path(url)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            expires_at = datetime.fromisoformat(str(payload["expires_at"]))
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            return None
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        data = payload.get("data")
        if not isinstance(data, dict):
            return None
        return {"expires_at": expires_at, "data": data}

    def _path(self, url: str) -> Path:
        return self.cache_dir / f"{url_cache_key(url)}.json"


def _now() -> datetime:
    return datetime.now(UTC)
