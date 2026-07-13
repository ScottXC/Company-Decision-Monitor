from __future__ import annotations

import argparse
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

DIST_APP_DIR = Path("dist") / "CompanyDecisionMonitor"
EXE_NAME = "CompanyDecisionMonitor.exe"
ZIP_PATH = Path("dist") / "CompanyDecisionMonitor_Portable.zip"
TEMP_ZIP_NAME = "CompanyDecisionMonitor_Portable.zip.tmp"
ZIP_ROOT = "CompanyDecisionMonitor"
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".git", "node_modules"}
EXCLUDED_SUFFIXES = {".log", ".tmp", ".temp", ".bak"}


@dataclass(frozen=True)
class PortablePackageResult:
    path: Path
    size_bytes: int
    file_count: int


def create_portable_zip(root: Path | None = None) -> PortablePackageResult:
    project_root = (root or Path.cwd()).resolve()
    dist_app_dir = project_root / DIST_APP_DIR
    exe_path = dist_app_dir / EXE_NAME
    zip_path = project_root / ZIP_PATH

    if not exe_path.exists():
        raise FileNotFoundError(
            f"{exe_path} does not exist. Run the PyInstaller build before creating the portable zip."
        )

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    temp_zip_path = zip_path.with_name(TEMP_ZIP_NAME)
    _unlink_with_retry(temp_zip_path)

    file_count = 0
    with zipfile.ZipFile(temp_zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(dist_app_dir.rglob("*")):
            if not path.is_file() or _should_exclude(path):
                continue
            relative = path.relative_to(dist_app_dir)
            archive.write(path, Path(ZIP_ROOT) / relative)
            file_count += 1
    _replace_with_retry(temp_zip_path, zip_path)

    return PortablePackageResult(
        path=zip_path,
        size_bytes=zip_path.stat().st_size,
        file_count=file_count,
    )


def _should_exclude(path: Path) -> bool:
    parts = set(path.parts)
    if EXCLUDED_PARTS & parts:
        return True
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    name = path.name.lower()
    return name.endswith((".old", ".orig")) or "setup" in name and path.suffix.lower() == ".exe"


def _unlink_with_retry(path: Path, *, attempts: int = 8, delay_seconds: float = 0.5) -> None:
    if not path.exists():
        return
    last_error: OSError | None = None
    for _attempt in range(attempts):
        try:
            path.unlink()
            return
        except OSError as exc:
            last_error = exc
            time.sleep(delay_seconds)
    raise RuntimeError(f"Cannot remove existing package file because it is still in use: {path}") from last_error


def _replace_with_retry(source: Path, target: Path, *, attempts: int = 8, delay_seconds: float = 0.5) -> None:
    last_error: OSError | None = None
    for _attempt in range(attempts):
        try:
            if target.exists():
                target.unlink()
            source.replace(target)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(delay_seconds)
    raise RuntimeError(f"Cannot replace portable package because the target is still in use: {target}") from last_error


def _format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size_bytes} B"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Company Decision Monitor portable zip.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root directory.")
    args = parser.parse_args()
    try:
        result = create_portable_zip(args.root)
    except Exception as exc:
        print(f"Failed to create portable zip: {exc}")
        return 1
    print(f"Portable zip: {result.path}")
    print(f"Size: {_format_size(result.size_bytes)}")
    print(f"Files: {result.file_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
