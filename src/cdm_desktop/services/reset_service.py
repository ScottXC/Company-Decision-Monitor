from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from cdm_desktop.db import DatabaseManager
from cdm_desktop.paths import AppPaths

APP_DATA_DIR_NAMES = ("CompanyDecisionMonitor", "Company Decision Monitor")


@dataclass(frozen=True)
class ResetResult:
    deleted_paths: tuple[Path, ...]
    recreated_data_dir: Path


def reset_user_data(
    db: DatabaseManager,
    paths: AppPaths,
    *,
    include_legacy_appdata: bool = True,
) -> ResetResult:
    """Delete local user data directories and recreate an empty database."""

    targets = reset_targets(paths, include_legacy_appdata=include_legacy_appdata)
    db.close()
    deleted: list[Path] = []
    for target in targets:
        if not _is_safe_reset_target(target, paths):
            raise ValueError(f"Unsafe reset target refused: {target}")
        if target.exists():
            shutil.rmtree(target)
            deleted.append(target)
    paths.ensure()
    db.initialize()
    return ResetResult(deleted_paths=tuple(deleted), recreated_data_dir=paths.app_data_dir)


def reset_targets(paths: AppPaths, *, include_legacy_appdata: bool = True) -> tuple[Path, ...]:
    targets: list[Path] = [paths.app_data_dir]
    if include_legacy_appdata:
        for env_name in ("APPDATA", "LOCALAPPDATA"):
            root = os.environ.get(env_name)
            if not root:
                continue
            for name in APP_DATA_DIR_NAMES:
                targets.append(Path(root) / name)
    unique: dict[str, Path] = {}
    for target in targets:
        unique[str(target.resolve(strict=False)).lower()] = target.resolve(strict=False)
    return tuple(unique.values())


def _is_safe_reset_target(target: Path, paths: AppPaths) -> bool:
    resolved = target.resolve(strict=False)
    current = paths.app_data_dir.resolve(strict=False)
    if resolved == current:
        return True
    if resolved.name not in APP_DATA_DIR_NAMES:
        return False
    parent = resolved.parent
    appdata_roots = {
        Path(value).resolve(strict=False)
        for value in (os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA"))
        if value
    }
    return parent in appdata_roots
