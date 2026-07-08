from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
EXE = DIST / "CompanyDecisionMonitor" / "CompanyDecisionMonitor.exe"
PORTABLE_ZIP = DIST / "CompanyDecisionMonitor_Portable.zip"
INSTALLER = DIST / "installer" / "CompanyDecisionMonitor_Setup.exe"

FORBIDDEN_NAMES = {
    ".env",
    "api_keys.json",
    "watchlist.json",
    "cdm.db",
}

FORBIDDEN_MARKERS = (
    b"xq_a_token",
    b"xueqiu_cookie",
    b"xueqiu_token",
    b"XueqiuScraper",
    b"XueqiuNewsCrawler",
    b"XueqiuApiProvider",
    b"XueqiuRagProvider",
)


def main() -> int:
    failures: list[str] = []
    for path in (EXE, PORTABLE_ZIP, INSTALLER):
        if not path.exists():
            failures.append(f"Missing artifact: {path}")
        elif path.stat().st_size <= 0:
            failures.append(f"Empty artifact: {path}")

    if PORTABLE_ZIP.exists():
        failures.extend(_validate_portable_zip(PORTABLE_ZIP))

    if (DIST / "CompanyDecisionMonitor").exists():
        failures.extend(_validate_dist_tree(DIST / "CompanyDecisionMonitor"))

    if failures:
        print("Release artifact validation failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Release artifact validation passed.")
    print(f"EXE: {EXE}")
    print(f"Portable ZIP: {PORTABLE_ZIP}")
    print(f"Installer: {INSTALLER}")
    return 0


def _validate_portable_zip(path: Path) -> list[str]:
    failures: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if not any(name.endswith("CompanyDecisionMonitor.exe") for name in names):
            failures.append("Portable ZIP does not contain CompanyDecisionMonitor.exe")
        for name in names:
            parts = {part.lower() for part in Path(name).parts}
            if parts & FORBIDDEN_NAMES:
                failures.append(f"Portable ZIP contains forbidden user/config data: {name}")
            if "__pycache__" in parts or ".pytest_cache" in parts or ".git" in parts:
                failures.append(f"Portable ZIP contains build/cache metadata: {name}")
    return failures


def _validate_dist_tree(path: Path) -> list[str]:
    failures: list[str] = []
    for file_path in path.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.name.lower() in FORBIDDEN_NAMES:
            failures.append(f"Dist contains forbidden user/config data: {file_path}")
        if file_path.suffix.lower() in {".pyc", ".pyo"}:
            continue
        try:
            data = file_path.read_bytes()
        except OSError as exc:
            failures.append(f"Could not read {file_path}: {exc}")
            continue
        lowered = data.lower()
        for marker in FORBIDDEN_MARKERS:
            if marker.lower() in lowered:
                failures.append(f"Dist contains forbidden marker {marker.decode(errors='ignore')}: {file_path}")
    return failures


if __name__ == "__main__":
    sys.exit(main())
