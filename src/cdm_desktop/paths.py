from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import PlatformDirs

from cdm_desktop import APP_NAME


@dataclass(frozen=True)
class AppPaths:
    app_data_dir: Path
    logs_dir: Path
    raw_documents_dir: Path
    exports_dir: Path
    cache_dir: Path
    db_path: Path

    def ensure(self) -> AppPaths:
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.raw_documents_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        return self


def get_app_paths() -> AppPaths:
    override = os.environ.get("CDM_DESKTOP_DATA_DIR")
    if override:
        data_dir = Path(override).expanduser().resolve()
    else:
        dirs = PlatformDirs(APP_NAME, appauthor=False, roaming=True)
        data_dir = Path(dirs.user_data_dir)

    return AppPaths(
        app_data_dir=data_dir,
        logs_dir=data_dir / "logs",
        raw_documents_dir=data_dir / "raw_documents",
        exports_dir=data_dir / "exports",
        cache_dir=data_dir / "cache",
        db_path=data_dir / "cdm.db",
    ).ensure()


def resource_path(relative: str) -> Path:
    package_dir = Path(__file__).resolve().parent
    return package_dir / "resources" / relative
