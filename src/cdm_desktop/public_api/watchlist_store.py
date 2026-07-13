from __future__ import annotations

import json
from dataclasses import dataclass

from cdm_desktop.paths import AppPaths, get_app_paths
from cdm_desktop.public_api.models import CompanyResult
from cdm_desktop.public_api.profile_service import CompanyProfileService
from cdm_desktop.public_api.provider_health import utc_timestamp


@dataclass(frozen=True)
class WatchlistRefreshSummary:
    succeeded: int
    failed: int
    skipped: int
    from_cache: int
    items: list[CompanyResult]


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
        target.last_status = "refreshing"
        self._write([target if item.dedupe_key() == dedupe_key else item for item in items])
        service = CompanyProfileService(self.paths)
        try:
            profile, statuses = service.get_profile(target)
        except Exception:  # noqa: BLE001
            profile = None
            statuses = []
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
        return self.refresh_all_with_summary().items

    def refresh_all_with_summary(self) -> WatchlistRefreshSummary:
        refreshed: list[CompanyResult] = []
        succeeded = failed = skipped = from_cache = 0
        for item in self.list_items():
            if not any([item.symbol, item.lei, item.wikidata_id, item.name, item.display_name]):
                skipped += 1
                item.last_status = "skipped_missing_identifier"
                refreshed.append(item)
                continue
            updated = self.refresh_item(item.dedupe_key())
            if updated is None:
                failed += 1
                continue
            refreshed.append(updated)
            if updated.from_cache:
                from_cache += 1
            if updated.last_status in {"refreshed", "refreshed_from_cache"}:
                succeeded += 1
            else:
                failed += 1
        if refreshed:
            self._write(refreshed)
        return WatchlistRefreshSummary(
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            from_cache=from_cache,
            items=refreshed,
        )

    def sorted_items(self, sort_by: str = "added_at") -> list[CompanyResult]:
        items = self.list_items()
        key_map = {
            "added_at": lambda item: item.added_at,
            "last_refreshed_at": lambda item: item.last_refreshed_at,
            "name": lambda item: item.display_name or item.name,
            "symbol": lambda item: item.symbol,
            "provider": lambda item: item.provider,
        }
        key_fn = key_map.get(sort_by, key_map["added_at"])
        reverse = sort_by in {"added_at", "last_refreshed_at"}
        return sorted(items, key=key_fn, reverse=reverse)

    def _write(self, items: list[CompanyResult]) -> None:
        self.paths.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _now() -> str:
    return utc_timestamp()
