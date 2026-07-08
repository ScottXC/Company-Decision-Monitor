from __future__ import annotations

import json

from cdm_desktop.paths import AppPaths, get_app_paths
from cdm_desktop.public_api.models import CompanyResult


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
        items[company.dedupe_key()] = company
        self._write(list(items.values()))

    def remove(self, dedupe_key: str) -> None:
        self._write([item for item in self.list_items() if item.dedupe_key() != dedupe_key])

    def contains(self, company: CompanyResult) -> bool:
        return company.dedupe_key() in {item.dedupe_key() for item in self.list_items()}

    def _write(self, items: list[CompanyResult]) -> None:
        self.paths.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
