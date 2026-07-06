from __future__ import annotations

import argparse
import shutil
from pathlib import Path

DEFAULT_DIRS = ["build", ".pytest_cache", ".ruff_cache", ".mypy_cache"]
FULL_DIRS = ["dist", "dist_installer"]
TEMP_SUFFIXES = {".log", ".tmp", ".temp"}


def clean(root: Path, *, full: bool = False) -> list[str]:
    root = root.resolve()
    removed: list[str] = []
    for name in DEFAULT_DIRS + (FULL_DIRS if full else []):
        removed.extend(_remove_path(root / name))
    for pycache in root.rglob("__pycache__"):
        removed.extend(_remove_path(pycache))
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in TEMP_SUFFIXES:
            removed.extend(_remove_path(path))
    if full:
        removed.extend(_remove_path(root / "dist" / "CompanyDecisionMonitor_Portable.zip"))
        removed.extend(_remove_path(root / "dist" / "installer" / "CompanyDecisionMonitor_Setup.exe"))
    return removed


def _remove_path(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    except OSError as exc:
        return [f"FAILED {path}: {exc}"]
    return [str(path)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean Company Decision Monitor build artifacts.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root directory.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Also remove dist/, old installers, and portable zip outputs.",
    )
    args = parser.parse_args()
    removed = clean(args.root, full=args.full)
    if not removed:
        print("Nothing to clean.")
        return 0
    print("Clean result:")
    for item in removed:
        print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
