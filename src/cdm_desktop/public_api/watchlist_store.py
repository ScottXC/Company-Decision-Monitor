from __future__ import annotations

import json
from datetime import datetime

from cdm_desktop.paths import AppPaths, get_app_paths
from cdm_desktop.public_api.models import CompanyResult
from cdm_desktop.public_api.profile_service import CompanyProfileService


class WatchlistStore:
    def __init__(self, paths: AppPaths | None = None) -> None:
        self.paths = paths or get_app_paths()
        self.path = self.paths.app_data_dir / "watchlist.json"

    def list_items(self) -> list[CompanyResult]:
        if not self.path.exists():
            return []
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(rows, list):
            return []
        return [CompanyResult.from_dict(row) for row in rows if isinstance(row, dict)]

    def add(self, company: CompanyResult) -> None:
        items = {item.dedupe_key(): item for item in self.list_items()}
        if not company.added_at:
            company.added_at = _now()
        if not company.id:
            company.id = company.dedupe_key()
        items[company.dedupe_key()] = company
        self._write(list(items.values()))

    def remove(self, dedupe_key: str) -> None:
        self._write([item for item in self.list_items() if item.dedupe_key() != dedupe_key])

    def contains(self, company: CompanyResult) -> bool:
        return company.dedupe_key() in {item.dedupe_key() for item in self.list_items()}

    def refresh_item(self, dedupe_key: str) -> CompanyResult | None:
        items = self.list_items()
        target = next((item for item in items if item.dedupe_key() == dedupe_key), None)
        if target is None:
            return None
        service = CompanyProfileService(self.paths)
        profile, statuses = service.get_profile(target)
        target.last_refreshed_at = _now()
        if profile:
            target.display_name = profile.display_name or target.display_name
            target.name = profile.display_name or target.name
            target.exchange = profile.exchange or target.exchange
            target.market = profile.market or target.market
            target.country = profile.country or target.country
            target.website = profile.website or target.website
            target.description = profile.description or target.description
            target.raw = {**target.raw, "latest_profile": profile.to_dict()}
            target.from_cache = profile.from_cache
            target.last_status = "refreshed_from_cache" if profile.from_cache else "refreshed"
        else:
            failed = next((status for status in statuses if status.state not in {"enabled", "empty"}), None)
            target.last_status = failed.message if failed else "refresh_failed"
        self._write([target if item.dedupe_key() == dedupe_key else item for item in items])
        return target

    def refresh_all(self) -> list[CompanyResult]:
        refreshed: list[CompanyResult] = []
        for item in self.list_items():
            updated = self.refresh_item(item.dedupe_key())
            if updated:
                refreshed.append(updated)
        return refreshed

    def _write(self, items: list[CompanyResult]) -> None:
        self.paths.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
