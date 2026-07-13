from __future__ import annotations

from pathlib import Path

import pytest
from scripts import build_windows
from scripts.validate_release_artifacts import _run_sqlite_self_test

from cdm_desktop import main as cdm_main


def test_find_sqlite_runtime_files_finds_current_python_runtime() -> None:
    runtime = build_windows.find_sqlite_runtime_files()

    assert runtime.sqlite_extension_path.exists()
    assert runtime.sqlite_extension_path.name.lower() == "_sqlite3.pyd"
    assert runtime.sqlite_dll_path.exists()
    assert runtime.sqlite_dll_path.name.lower() == "sqlite3.dll"
    assert runtime.checked_paths


def test_find_sqlite_runtime_files_reports_checked_paths_when_dll_missing(tmp_path: Path) -> None:
    extension = tmp_path / "_sqlite3.pyd"
    extension.write_bytes(b"placeholder")

    with pytest.raises(FileNotFoundError) as exc_info:
        build_windows.find_sqlite_runtime_files(
            candidate_roots=[tmp_path],
            sqlite_extension_path=extension,
        )

    message = str(exc_info.value)
    assert "sqlite3.dll was not found" in message
    assert str(tmp_path / "DLLs" / "sqlite3.dll") in message
    assert str(tmp_path / "Library" / "bin" / "sqlite3.dll") in message


def test_pyinstaller_command_collects_sqlite_and_does_not_reference_pysqlite2() -> None:
    command = build_windows._pyinstaller_command(Path.cwd())
    command_text = " ".join(command).lower()

    assert "--hidden-import sqlite3" in command_text
    assert "--hidden-import _sqlite3" in command_text
    assert "sqlite3.dll" in command_text
    assert "_sqlite3.pyd" in command_text
    assert "pysqlite2" not in command_text


def test_project_sqlalchemy_hook_does_not_request_pysqlite2() -> None:
    hook_text = (Path.cwd() / "pyinstaller_hooks" / "hook-sqlalchemy.py").read_text(encoding="utf-8")

    assert "pysqlite2" not in hook_text


def test_sqlite_self_test_succeeds_without_importing_gui(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_gui_imported(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("GUI path should not be imported during sqlite self-test")

    monkeypatch.setattr(cdm_main, "get_app_paths", fail_if_gui_imported, raising=False)

    assert cdm_main.main(["--self-test", "sqlite"]) == 0


def test_sqlite_self_test_output_confirms_fts5_and_index(capsys) -> None:
    assert cdm_main.main(["--self-test", "sqlite"]) == 0
    output = capsys.readouterr().out.lower()

    assert "fts5=ok" in output
    assert "index=ok" in output


def test_release_validator_sqlite_self_test_handles_missing_exe(tmp_path: Path) -> None:
    result = _run_sqlite_self_test(tmp_path / "missing.exe")

    assert result["passed"] is False
    assert "could not start" in str(result["message"])
