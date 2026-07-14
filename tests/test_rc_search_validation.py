from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.validate_symbol_universe import validate_index

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.key_store import ApiKeyStore
from cdm_desktop.public_api.models import ProviderMeta
from cdm_desktop.public_api.providers import SymbolUniverseProvider
from cdm_desktop.public_api.search_index_manager import SearchIndexManager


def _paths(root: Path) -> AppPaths:
    return AppPaths(root, root / "logs", root / "raw", root / "exports", root / "cache", root / "cdm.db").ensure()


def _meta() -> ProviderMeta:
    return ProviderMeta(
        "symbol_universe", "Index", "symbol_universe", "global", "search", False,
        None, "bundled", "", True,
    )


def test_missing_index_is_reported_without_crash(tmp_path: Path) -> None:
    report = validate_index(tmp_path / "missing.sqlite")
    assert report["failures"] == ["symbol universe index is missing"]


def test_corrupted_index_is_reported_without_raw_traceback(tmp_path: Path) -> None:
    path = tmp_path / "corrupted.sqlite"
    path.write_bytes(b"not a sqlite database")
    report = validate_index(path)
    assert report["failures"]
    assert "traceback" not in " ".join(report["failures"]).casefold()


def test_missing_fts_ngram_metadata_and_schema_block_validation(tmp_path: Path) -> None:
    path = tmp_path / "incomplete.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript(
        "CREATE TABLE symbols(id INTEGER PRIMARY KEY, normalized_symbol TEXT, normalized_name TEXT);"
        "CREATE TABLE aliases(symbol_id INTEGER, normalized_alias TEXT);"
        "CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);"
        "INSERT INTO metadata VALUES('schema_version','1');"
    )
    connection.close()
    report = validate_index(path)
    failures = " ".join(report["failures"])
    assert "symbols_fts" in failures
    assert "name_ngrams" in failures
    assert "schema_version" in failures


def test_provider_returns_structured_error_for_corrupted_index(tmp_path: Path) -> None:
    path = tmp_path / "corrupted.sqlite"
    path.write_bytes(b"broken")
    SearchIndexManager.reset_for_tests()
    paths = _paths(tmp_path / "appdata")
    provider = SymbolUniverseProvider(_meta(), ApiKeyStore(paths), object())  # type: ignore[arg-type]
    provider.index_path = path
    provider.index_manager = SearchIndexManager.for_path(path)
    rows, _news, error = provider.search("TEST")
    assert rows == []
    assert error and error.state == "index_corrupted"
