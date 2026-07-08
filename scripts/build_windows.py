from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from clean_build import clean
from package_portable import PortablePackageResult, create_portable_zip

APP_NAME = "CompanyDecisionMonitor"
EXE_NAME = "CompanyDecisionMonitor.exe"
VERSION_NAME = "v0.1.2-core-functions"


@dataclass(frozen=True)
class Artifact:
    label: str
    path: Path
    exists: bool
    size_bytes: int = 0


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

        _phase("代码检查")
        _run([_tool("ruff"), "check", "src", "tests", "scripts"], root)
        _run([_tool("pytest")], root)

        _phase("PyInstaller 构建")
        _run(_pyinstaller_command(root), root)
        _verify_pyinstaller_output(dist_app_dir, exe_path)
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
    ]
    if icon_path.exists():
        command.extend(["--icon", str(icon_path)])
    for module in [
        "pandas",
        "numpy",
        "scipy",
        "sklearn",
        "torch",
        "torchvision",
        "transformers",
        "tensorflow",
        "pyarrow",
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
    for dll in _python_runtime_dlls():
        command.extend(["--add-binary", f"{dll};."])
    command.extend(
        [
            "--add-data",
            str(root / "src" / "cdm_desktop" / "resources") + ";cdm_desktop/resources",
            "--add-data",
            str(root / "src" / "cdm_desktop" / "ui" / "styles.qss") + ";cdm_desktop/ui",
            str(root / "src" / "cdm_desktop" / "main.py"),
        ]
    )
    return command


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
        dist_app_dir / "_internal" / "cdm_desktop" / "ui" / "styles.qss",
    ]
    missing = [path for path in required_files if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing packaged static resources: " + ", ".join(str(path) for path in missing))

    forbidden_names = {".git", "src", "tests", "node_modules", "build"}
    forbidden_found = [
        path for path in dist_app_dir.rglob("*") if any(part in forbidden_names for part in path.parts)
    ]
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
