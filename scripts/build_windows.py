from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    from clean_build import clean
    from package_portable import PortablePackageResult, create_portable_zip
except ModuleNotFoundError:
    from scripts.clean_build import clean
    from scripts.package_portable import PortablePackageResult, create_portable_zip

APP_NAME = "CompanyDecisionMonitor"
EXE_NAME = "CompanyDecisionMonitor.exe"
VERSION_NAME = "v0.1.4-generalized-search-performance-rc1"
SYMBOL_UNIVERSE_INDEX = Path("src") / "cdm_desktop" / "resources" / "symbol_universe" / "symbol_universe.sqlite"
CHINA_HK_INDEX = Path("src") / "cdm_desktop" / "resources" / "china_hk_symbols" / "china_hk_symbols.sqlite"


@dataclass(frozen=True)
class Artifact:
    label: str
    path: Path
    exists: bool
    size_bytes: int = 0


@dataclass(frozen=True)
class SqliteRuntimeFiles:
    sqlite_extension_path: Path
    sqlite_dll_path: Path
    checked_paths: tuple[Path, ...]


def find_iscc() -> tuple[str | None, list[str]]:
    candidates = [
        shutil.which("ISCC.exe"),
        shutil.which("iscc.exe"),
        os.environ.get("INNO_SETUP_COMPILER"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]

    checked: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(str(candidate).strip().strip('"'))
        checked.append(str(path))
        if path.exists():
            return str(path), checked
    return None, checked


def find_sqlite_runtime_files(
    *,
    candidate_roots: list[Path] | None = None,
    sqlite_extension_path: Path | None = None,
) -> SqliteRuntimeFiles:
    if sqlite_extension_path is None:
        try:
            import _sqlite3
            import sqlite3  # noqa: F401
        except Exception as exc:
            raise RuntimeError(f"Cannot import sqlite3/_sqlite3 in build Python: {exc}") from exc
        sqlite_extension_path = Path(_sqlite3.__file__).resolve()
    else:
        sqlite_extension_path = sqlite_extension_path.resolve()

    if not sqlite_extension_path.exists():
        raise FileNotFoundError(f"_sqlite3 extension was not found: {sqlite_extension_path}")

    roots: list[Path] = []
    if candidate_roots is None:
        for value in (sys.prefix, sys.base_prefix, os.environ.get("CONDA_PREFIX")):
            if value:
                path = Path(value).resolve()
                if path not in roots:
                    roots.append(path)
    else:
        for root in candidate_roots:
            path = root.resolve()
            if path not in roots:
                roots.append(path)

    candidates: list[Path] = []
    for root in roots:
        candidates.extend(
            [
                root / "DLLs" / "sqlite3.dll",
                root / "Library" / "bin" / "sqlite3.dll",
            ]
        )
    candidates.append(sqlite_extension_path.parent / "sqlite3.dll")

    checked: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in checked:
            continue
        checked.append(resolved)
        if resolved.exists():
            return SqliteRuntimeFiles(
                sqlite_extension_path=sqlite_extension_path,
                sqlite_dll_path=resolved,
                checked_paths=tuple(checked),
            )

    checked_text = "\n".join(f"- {path}" for path in checked)
    raise FileNotFoundError(
        "sqlite3.dll was not found for the current Python runtime. Checked paths:\n" + checked_text
    )


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    dist_app_dir = root / "dist" / APP_NAME
    exe_path = dist_app_dir / EXE_NAME
    portable_zip = root / "dist" / f"{APP_NAME}_Portable.zip"
    installer_script = root / "installer" / "CompanyDecisionMonitor.iss"
    setup_path = root / "dist" / "installer" / "CompanyDecisionMonitor_Setup.exe"

    try:
        _phase("清理旧构建")
        clean(root, full=True)
        (root / "build").mkdir(parents=True, exist_ok=True)

        _phase("代码检查")
        _run([_tool("ruff"), "check", "src", "tests", "scripts"], root)
        pytest_temp = f"build/pytest-temp-{os.getpid()}"
        _run([_tool("pytest"), f"--basetemp={pytest_temp}"], root)

        _phase("内置开源证券索引检查")
        _ensure_symbol_universe_index(root)
        _ensure_china_hk_index(root)

        _phase("PyInstaller 构建")
        _run(_pyinstaller_command(root), root)
        _verify_pyinstaller_output(dist_app_dir, exe_path)
        _run_frozen_sqlite_self_test(exe_path, root)
        _run_frozen_akshare_self_test(exe_path, root)
        print(f"EXE: {exe_path}")

        _phase("便携版 zip 生成")
        portable_result = create_portable_zip(root)
        print(f"Portable zip: {portable_result.path}")
        print(f"Portable files: {portable_result.file_count}")
        print(f"Portable size: {_format_size(portable_result.size_bytes)}")

        _phase("Inno Setup 安装包生成")
        iscc, checked = find_iscc()
        print("Checked ISCC paths:")
        for item in checked:
            print(f"- {item}")
        if not iscc:
            raise RuntimeError("ISCC.exe 未找到，无法生成安装包。")
        print(f"Using ISCC: {iscc}")
        _build_installer(iscc, installer_script, setup_path, dist_app_dir, exe_path, root)

        _phase("交付物汇总")
        _print_summary(
            [
                Artifact("EXE", exe_path, exe_path.exists(), _size(exe_path)),
                Artifact("Portable ZIP", portable_zip, portable_zip.exists(), _size(portable_zip)),
                Artifact("Setup", setup_path, setup_path.exists(), _size(setup_path)),
            ],
            portable_result,
        )
    except Exception as exc:
        print(f"BUILD FAILED: {exc}")
        return 1
    return 0


def _tool(name: str) -> str:
    resolved = shutil.which(name)
    return resolved or name


def _python_runtime_dlls() -> list[Path]:
    library_bin = Path(sys.prefix) / "Library" / "bin"
    names = [
        "libcrypto-3-x64.dll",
        "libssl-3-x64.dll",
        "ffi.dll",
        "libexpat.dll",
        "liblzma.dll",
        "libbz2.dll",
    ]
    return [library_bin / name for name in names if (library_bin / name).exists()]


def _phase(title: str) -> None:
    print("")
    print("=" * 72)
    print(title)
    print("=" * 72)


def _run(command: list[str], cwd: Path) -> None:
    print("> " + " ".join(command))
    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {' '.join(command)}")


def _pyinstaller_command(root: Path) -> list[str]:
    icon_path = root / "src" / "cdm_desktop" / "resources" / "app.ico"
    sqlite_runtime = find_sqlite_runtime_files()
    print(f"SQLite extension: {sqlite_runtime.sqlite_extension_path}")
    print(f"SQLite runtime DLL: {sqlite_runtime.sqlite_dll_path}")
    print("SQLite DLL checked paths:")
    for checked_path in sqlite_runtime.checked_paths:
        print(f"- {checked_path}")

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        APP_NAME,
        "--additional-hooks-dir",
        str(root / "pyinstaller_hooks"),
    ]
    if icon_path.exists():
        command.extend(["--icon", str(icon_path)])
    for module in ["sqlite3", "_sqlite3"]:
        command.extend(["--hidden-import", module])
    command.extend(["--collect-submodules", "akshare"])
    command.extend(["--collect-data", "akshare"])
    command.extend(["--collect-all", "py_mini_racer"])
    for module in [
        "scipy",
        "sklearn",
        "torch",
        "torchvision",
        "transformers",
        "tensorflow",
        "pyarrow",
        "financedatabase",
        "financetoolkit",
        "yfinance",
        "redis",
        "psycopg",
        "psycopg2",
        "psycopg_binary",
        "asyncpg",
        "pg8000",
        "pymysql",
        "MySQLdb",
        "pytest",
        "mypy",
        "ruff",
        "bandit",
        "pip_audit",
    ]:
        command.extend(["--exclude-module", module])
    binaries = [
        sqlite_runtime.sqlite_dll_path,
        sqlite_runtime.sqlite_extension_path,
        *_python_runtime_dlls(),
    ]
    added_binaries: set[Path] = set()
    for dll in binaries:
        resolved = dll.resolve()
        if resolved in added_binaries:
            continue
        added_binaries.add(resolved)
        command.extend(["--add-binary", f"{dll};."])
    command.extend(
        [
            "--add-data",
            str(root / "src" / "cdm_desktop" / "resources") + ";cdm_desktop/resources",
            "--add-data",
            str(root / "src" / "cdm_desktop" / "ui" / "theme" / "light.qss") + ";cdm_desktop/ui/theme",
            "--add-data",
            str(root / "src" / "cdm_desktop" / "ui" / "theme" / "dark.qss") + ";cdm_desktop/ui/theme",
            "--add-data",
            str(root / "THIRD_PARTY_NOTICES.md") + ";.",
            "--add-data",
            str(root / "third_party" / "licenses") + ";third_party/licenses",
            str(root / "src" / "cdm_desktop" / "main.py"),
        ]
    )
    return command


def _ensure_symbol_universe_index(root: Path) -> None:
    index_path = root / SYMBOL_UNIVERSE_INDEX
    if not index_path.exists():
        print("Symbol universe index missing; generating from FinanceDatabase.")
        _run([sys.executable, "scripts/build_symbol_universe.py"], root)
    if not index_path.exists():
        raise FileNotFoundError(f"Symbol universe index was not generated: {index_path}")
    connection = sqlite3.connect(f"{index_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        objects = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master")}
        if not {"symbols", "aliases", "symbols_fts", "name_ngrams"}.issubset(objects):
            raise RuntimeError("Symbol universe index is missing FTS5 or n-gram search objects.")
    finally:
        connection.close()
    size_mb = index_path.stat().st_size / 1024 / 1024
    print(f"Symbol universe index: {index_path}")
    print(f"Symbol universe index size: {size_mb:.2f} MB")


def _ensure_china_hk_index(root: Path) -> None:
    index_path = root / CHINA_HK_INDEX
    if not index_path.exists():
        raise FileNotFoundError(
            "China/HK index is missing. Run scripts/build_china_hk_symbol_index.py before packaging."
        )
    _run([sys.executable, "scripts/validate_china_hk_index.py"], root)
    print(f"China/HK index: {index_path} ({_format_size(index_path.stat().st_size)})")


def _verify_pyinstaller_output(dist_app_dir: Path, exe_path: Path) -> None:
    if not dist_app_dir.exists():
        raise FileNotFoundError(f"PyInstaller output directory does not exist: {dist_app_dir}")
    if not exe_path.exists():
        raise FileNotFoundError(f"PyInstaller executable does not exist: {exe_path}")
    if not (dist_app_dir / "_internal").exists():
        raise FileNotFoundError(f"PyInstaller dependency directory is missing: {dist_app_dir / '_internal'}")

    required_files = [
        dist_app_dir / "_internal" / "cdm_desktop" / "resources" / "app.ico",
        dist_app_dir / "_internal" / "cdm_desktop" / "resources" / "app.png",
        dist_app_dir / "_internal" / "cdm_desktop" / "resources" / "symbol_universe" / "symbol_universe.sqlite",
        dist_app_dir / "_internal" / "cdm_desktop" / "resources" / "china_hk_symbols" / "china_hk_symbols.sqlite",
        dist_app_dir / "_internal" / "cdm_desktop" / "ui" / "theme" / "light.qss",
        dist_app_dir / "_internal" / "cdm_desktop" / "ui" / "theme" / "dark.qss",
        dist_app_dir / "_internal" / "THIRD_PARTY_NOTICES.md",
        dist_app_dir / "_internal" / "third_party" / "licenses" / "RapidFuzz_LICENSE.txt",
        dist_app_dir / "_internal" / "third_party" / "licenses" / "cleanco_LICENSE.txt",
        dist_app_dir / "_internal" / "third_party" / "licenses" / "FinanceDatabase_LICENSE.txt",
        dist_app_dir / "_internal" / "third_party" / "licenses" / "AKShare_LICENSE.txt",
        dist_app_dir / "_internal" / "sqlite3.dll",
        dist_app_dir / "_internal" / "_sqlite3.pyd",
    ]
    missing = [path for path in required_files if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing packaged static resources: " + ", ".join(str(path) for path in missing))

    forbidden_names = {".git", "src", "tests", "node_modules", "build"}
    forbidden_found = []
    for path in dist_app_dir.rglob("*"):
        relative_parts = path.relative_to(dist_app_dir).parts
        if any(part.endswith(".dist-info") for part in relative_parts):
            continue
        if any(part in forbidden_names for part in relative_parts):
            forbidden_found.append(path)
    if forbidden_found:
        raise RuntimeError(
            "Forbidden source/cache directories found in PyInstaller output: "
            + ", ".join(str(path) for path in forbidden_found[:10])
        )

    file_count = sum(1 for path in dist_app_dir.rglob("*") if path.is_file())
    if file_count < 5:
        raise RuntimeError(f"PyInstaller output looks incomplete: only {file_count} files found")
    print(f"PyInstaller files: {file_count}")
    print("Config files: user API keys are stored only in AppData and are not packaged")
    print("Old product data check: no source/test directories are included in dist output")


def _run_frozen_sqlite_self_test(exe_path: Path, root: Path) -> None:
    if not exe_path.exists():
        raise FileNotFoundError(f"Cannot run SQLite self-test because executable is missing: {exe_path}")
    print("Running frozen SQLite self-test")
    _run([str(exe_path), "--self-test", "sqlite"], root)


def _run_frozen_akshare_self_test(exe_path: Path, root: Path) -> None:
    print("Running frozen AKShare import self-test")
    report = root / "build" / "akshare-self-test.txt"
    report.unlink(missing_ok=True)
    environment = {**os.environ, "CDM_SELF_TEST_REPORT": str(report)}
    completed = subprocess.run([str(exe_path), "--self-test", "akshare"], cwd=root, env=environment, check=False)
    message = report.read_text(encoding="utf-8") if report.exists() else "No AKShare self-test report was produced."
    print(message)
    if completed.returncode != 0:
        raise RuntimeError(message)


def _build_installer(
    iscc: str,
    installer_script: Path,
    setup_path: Path,
    dist_app_dir: Path,
    exe_path: Path,
    root: Path,
) -> None:
    if not installer_script.exists():
        raise FileNotFoundError(f".iss file path is wrong: {installer_script}")
    if not dist_app_dir.exists():
        raise FileNotFoundError(f"Source path does not exist: {dist_app_dir}")
    if not exe_path.exists():
        raise FileNotFoundError(f"Main executable does not exist: {exe_path}")
    if setup_path.exists():
        setup_path.unlink()
    setup_path.parent.mkdir(parents=True, exist_ok=True)
    _run([iscc, str(installer_script)], root)
    if not setup_path.exists():
        raise FileNotFoundError(
            "Inno Setup finished but setup file was not generated. "
            f"Check OutputDir/OutputBaseFilename in {installer_script}."
        )
    if setup_path.stat().st_size <= 1024 * 1024:
        raise RuntimeError(f"Installer looks too small and may be incomplete: {setup_path}")
    print(f"Setup: {setup_path}")


def _print_summary(artifacts: list[Artifact], portable_result: PortablePackageResult) -> None:
    for artifact in artifacts:
        status = "OK" if artifact.exists else "MISSING"
        print(f"{artifact.label}: {status} | {artifact.path} | {_format_size(artifact.size_bytes)}")
    print(f"Portable ZIP file count: {portable_result.file_count}")


def _size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def _format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size_bytes} B"


if __name__ == "__main__":
    raise SystemExit(main())
