from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "src" / "cdm_desktop" / "resources" / "china_hk_symbols" / "china_hk_symbols.sqlite"
CORE_SYMBOLS = (
    "SH600519", "SZ002594", "SH601318", "SZ300750", "HK00700", "HK09988",
    "HK03690", "HK01810", "HK09618", "HK01024", "HK00005",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_INDEX)
    args = parser.parse_args()
    path = args.path.resolve()
    failures: list[str] = []
    if not path.exists():
        print(f"China/HK index validation failed: missing {path}")
        return 1
    connection = sqlite3.connect(path)
    try:
        objects = {row[0]: row[1] for row in connection.execute("SELECT name,type FROM sqlite_master")}
        for name in ("symbols", "aliases", "metadata", "name_ngrams"):
            if name not in objects:
                failures.append(f"missing table: {name}")
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(symbols)")}
        alias_indexes = {row[1] for row in connection.execute("PRAGMA index_list(aliases)")}
        ngram_indexes = {row[1] for row in connection.execute("PRAGMA index_list(name_ngrams)")}
        if "idx_china_hk_symbol" not in indexes or "idx_china_hk_name" not in indexes:
            failures.append("required symbol/name indexes are missing")
        if "idx_china_hk_alias" not in alias_indexes:
            failures.append("required alias index is missing")
        if "idx_name_ngrams_gram" not in ngram_indexes:
            failures.append("required n-gram index is missing")
        metadata = {str(k): str(v) for k, v in connection.execute("SELECT key,value FROM metadata")}
        counts = {
            "records": int(connection.execute("SELECT count(*) FROM symbols").fetchone()[0]),
            "a_shares": int(connection.execute("SELECT count(*) FROM symbols WHERE market IN ('SH','SZ','BJ')").fetchone()[0]),
            "hk_shares": int(connection.execute("SELECT count(*) FROM symbols WHERE market='HK'").fetchone()[0]),
            "aliases": int(connection.execute("SELECT count(*) FROM aliases").fetchone()[0]),
            "fts": int(connection.execute("SELECT count(*) FROM symbols_fts").fetchone()[0]) if "symbols_fts" in objects else 0,
            "ngrams": int(connection.execute("SELECT count(*) FROM name_ngrams").fetchone()[0]),
        }
        if counts["records"] < 1000 or counts["a_shares"] < 1000 or counts["hk_shares"] < 100:
            failures.append(f"implausible record counts: {counts}")
        placeholders = ",".join("?" for _ in CORE_SYMBOLS)
        present = {row[0] for row in connection.execute(f"SELECT symbol FROM symbols WHERE symbol IN ({placeholders})", CORE_SYMBOLS)}
        missing = sorted(set(CORE_SYMBOLS) - present)
        if missing:
            failures.append(f"missing core securities: {', '.join(missing)}")
        duplicates = int(connection.execute("SELECT count(*) FROM (SELECT symbol FROM symbols GROUP BY symbol HAVING count(*)>1)").fetchone()[0])
        if duplicates:
            failures.append(f"duplicate symbols: {duplicates}")
        empty_names = int(connection.execute("SELECT count(*) FROM symbols WHERE trim(name)='' ").fetchone()[0])
        if empty_names:
            failures.append(f"empty names: {empty_names}")
        sensitive = connection.execute(
            "SELECT count(*) FROM symbols WHERE lower(name) LIKE '%xq_a_token%' OR lower(source_detail) LIKE '%cookie%'"
        ).fetchone()[0]
        if sensitive:
            failures.append("sensitive cookie/token marker found")
        if "symbols_fts" in objects:
            try:
                connection.execute("SELECT rowid FROM symbols_fts WHERE symbols_fts MATCH ? LIMIT 1", ('"tencent"*',)).fetchone()
            except sqlite3.OperationalError as exc:
                failures.append(f"FTS5 query failed: {exc}")
    finally:
        connection.close()
    report = {"path": str(path), "size_bytes": path.stat().st_size, "metadata": metadata, "counts": counts, "failures": failures}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
