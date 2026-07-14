from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "src" / "cdm_desktop" / "resources" / "symbol_universe" / "symbol_universe.sqlite"
REQUIRED_TABLES = {"symbols", "aliases", "symbols_fts", "name_ngrams", "metadata"}
REQUIRED_INDEXES = {
    "idx_symbols_normalized_symbol",
    "idx_symbols_normalized_name",
    "idx_aliases_normalized_alias",
    "idx_aliases_symbol_id",
    "idx_name_ngrams_gram",
    "idx_name_ngrams_symbol_id",
}


def validate_index(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    failures: list[str] = []
    report: dict[str, Any] = {"path": str(resolved), "failures": failures}
    if not resolved.exists():
        failures.append("symbol universe index is missing")
        return report
    report["size_bytes"] = resolved.stat().st_size
    try:
        connection = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        failures.append(f"cannot open SQLite index: {type(exc).__name__}")
        return report
    try:
        quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        report["quick_check"] = quick_check
        if quick_check.casefold() != "ok":
            failures.append(f"SQLite quick_check failed: {quick_check}")
        objects = {
            str(row[0]): str(row[1])
            for row in connection.execute("SELECT name,type FROM sqlite_master")
        }
        missing_tables = sorted(REQUIRED_TABLES - set(objects))
        if missing_tables:
            failures.append("missing search objects: " + ", ".join(missing_tables))
        metadata = (
            {str(key): _decode(value) for key, value in connection.execute("SELECT key,value FROM metadata")}
            if "metadata" in objects
            else {}
        )
        report["metadata"] = metadata
        if str(metadata.get("schema_version", "")) != "2":
            failures.append("schema_version must be 2")
        counts = {
            "symbols": _count(connection, "symbols", objects),
            "aliases": _count(connection, "aliases", objects),
            "fts": _count(connection, "symbols_fts", objects),
            "ngrams": _count(connection, "name_ngrams", objects),
        }
        report["counts"] = counts
        if counts["symbols"] < 50_000 or counts["aliases"] < counts["symbols"]:
            failures.append(f"implausible symbols/aliases counts: {counts}")
        if counts["fts"] != counts["symbols"] or counts["ngrams"] < counts["symbols"]:
            failures.append(f"implausible FTS/n-gram counts: {counts}")
        indexes = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
            )
        }
        report["indexes"] = sorted(indexes)
        missing_indexes = sorted(REQUIRED_INDEXES - indexes)
        if missing_indexes:
            failures.append("missing indexes: " + ", ".join(missing_indexes))
        if "sqlite_stat1" not in objects:
            failures.append("ANALYZE statistics are missing")
        suspicious_objects = [
            name for name in objects if any(marker in name.casefold() for marker in ("cache", "watchlist", "history", "pytest"))
        ]
        if suspicious_objects:
            failures.append("runtime/test tables found: " + ", ".join(sorted(suspicious_objects)))
        metadata_text = json.dumps(metadata, ensure_ascii=False).casefold()
        if any(marker in metadata_text for marker in ("api_key", "xq_a_token", "cookie", "bearer token")):
            failures.append("sensitive key/cookie/token marker found in metadata")
        if not connection.execute(
            "SELECT id FROM symbols WHERE normalized_symbol=? LIMIT 1", ("AAPL",)
        ).fetchone():
            failures.append("core exact-symbol query failed")
        if "symbols_fts" in objects and not connection.execute(
            "SELECT rowid FROM symbols_fts WHERE symbols_fts MATCH ? LIMIT 1", ('"apple"*',)
        ).fetchone():
            failures.append("FTS5 query failed")
        if "name_ngrams" in objects and not connection.execute(
            "SELECT symbol_id FROM name_ngrams WHERE gram=? LIMIT 1", ("app",)
        ).fetchone():
            failures.append("n-gram query failed")
    except sqlite3.Error as exc:
        failures.append(f"SQLite validation error: {type(exc).__name__}: {exc}")
    finally:
        connection.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the bundled global symbol universe.")
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_INDEX)
    args = parser.parse_args()
    report = validate_index(args.path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["failures"] else 0


def _count(connection: sqlite3.Connection, table: str, objects: dict[str, str]) -> int:
    if table not in objects:
        return 0
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _decode(value: Any) -> Any:
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
