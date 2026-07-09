from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
EXE = DIST / "CompanyDecisionMonitor" / "CompanyDecisionMonitor.exe"
PORTABLE_ZIP = DIST / "CompanyDecisionMonitor_Portable.zip"
INSTALLER = DIST / "installer" / "CompanyDecisionMonitor_Setup.exe"
INSTALLER_SCRIPT = ROOT / "installer" / "CompanyDecisionMonitor.iss"
REPORTS = ROOT / "reports"
REPORT_PATH = REPORTS / "release_artifact_report.json"

FORBIDDEN_FILE_NAMES = {
    ".env",
    "api_keys.json",
    "watchlist.json",
    "cdm.db",
}

FORBIDDEN_PATH_PARTS = {
    ".git",
    "appdata",
    "build",
    "reports",
    "tests",
    "src",
    "__pycache__",
    ".pytest_cache",
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

FORBIDDEN_INSTALLER_REFERENCES = (
    ".env",
    "api_keys.json",
    "watchlist.json",
    "AppData",
    "{userappdata}",
    "cache",
    "reports",
)


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []
    failures: list[str] = []

    for label, path in (("exe", EXE), ("portable_zip", PORTABLE_ZIP), ("installer", INSTALLER)):
        ok = path.exists() and path.stat().st_size > 0
        checks.append({"check": f"{label}_exists", "status": "passed" if ok else "failed", "path": str(path)})
        if not ok:
            failures.append(f"Missing or empty artifact: {path}")

    if PORTABLE_ZIP.exists():
        zip_failures = _validate_portable_zip(PORTABLE_ZIP)
        failures.extend(zip_failures)
        checks.append({"check": "portable_zip_contents", "status": "passed" if not zip_failures else "failed", "failures": zip_failures})

    dist_root = DIST / "CompanyDecisionMonitor"
    if dist_root.exists():
        dist_failures = _validate_dist_tree(dist_root)
        failures.extend(dist_failures)
        checks.append({"check": "dist_tree_sensitive_markers", "status": "passed" if not dist_failures else "failed", "failures": dist_failures})

    installer_failures = _validate_installer_script(INSTALLER_SCRIPT)
    failures.extend(installer_failures)
    checks.append({"check": "installer_script_references", "status": "passed" if not installer_failures else "failed", "failures": installer_failures})

    report = {
        "version": "v0.1.2",
        "checks": checks,
        "failures": failures,
        "artifacts": {
            "exe": _artifact(EXE),
            "portable_zip": _artifact(PORTABLE_ZIP),
            "installer": _artifact(INSTALLER),
        },
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if failures:
        print("Release artifact validation failed:")
        for failure in failures:
            print(f"- {failure}")
        print(f"Report: {REPORT_PATH}")
        return 1

    print("Release artifact validation passed.")
    print(f"EXE: {EXE}")
    print(f"Portable ZIP: {PORTABLE_ZIP}")
    print(f"Installer: {INSTALLER}")
    print(f"Report: {REPORT_PATH}")
    return 0


def _validate_portable_zip(path: Path) -> list[str]:
    failures: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if not any(name.replace("\\", "/").endswith("CompanyDecisionMonitor.exe") for name in names):
            failures.append("Portable ZIP does not contain CompanyDecisionMonitor.exe")
        for name in names:
            normalized = name.replace("\\", "/")
            parts = {part.lower() for part in Path(normalized).parts}
            file_name = Path(normalized).name.lower()
            if file_name in FORBIDDEN_FILE_NAMES:
                failures.append(f"Portable ZIP contains forbidden user/config data: {name}")
            if parts & FORBIDDEN_PATH_PARTS:
                failures.append(f"Portable ZIP contains forbidden path part: {name}")
            if file_name.endswith((".log", ".db", ".sqlite", ".sqlite3")):
                failures.append(f"Portable ZIP contains runtime data file: {name}")
    return failures


def _validate_dist_tree(path: Path) -> list[str]:
    failures: list[str] = []
    for file_path in path.rglob("*"):
        if not file_path.is_file():
            continue
        parts = {part.lower() for part in file_path.relative_to(path).parts}
        if file_path.name.lower() in FORBIDDEN_FILE_NAMES:
            failures.append(f"Dist contains forbidden user/config data: {file_path}")
        if parts & FORBIDDEN_PATH_PARTS:
            failures.append(f"Dist contains forbidden path part: {file_path}")
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


def _validate_installer_script(path: Path) -> list[str]:
    if not path.exists():
        return [f"Installer script missing: {path}"]
    text = path.read_text(encoding="utf-8", errors="ignore")
    failures = []
    for marker in FORBIDDEN_INSTALLER_REFERENCES:
        if marker.lower() in text.lower():
            failures.append(f"Installer script references forbidden marker: {marker}")
    return failures


def _artifact(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
    }


if __name__ == "__main__":
    sys.exit(main())
