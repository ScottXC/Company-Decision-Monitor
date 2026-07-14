from __future__ import annotations

import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEXES = (
    ROOT / "src" / "cdm_desktop" / "resources" / "symbol_universe" / "symbol_universe.sqlite",
    ROOT / "src" / "cdm_desktop" / "resources" / "china_hk_symbols" / "china_hk_symbols.sqlite",
)


def main() -> int:
    for path in INDEXES:
        if not path.exists():
            print(f"Missing index: {path}")
            return 1
        upgrade_index(path)
    return 0


def upgrade_index(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(symbols)")}
        china_hk = "chinese_name" in columns
        connection.execute("DROP TABLE IF EXISTS name_ngrams")
        connection.executescript(
            """
            CREATE TABLE name_ngrams (
                gram TEXT NOT NULL, symbol_id INTEGER NOT NULL, field_type TEXT NOT NULL,
                position INTEGER NOT NULL, confidence INTEGER NOT NULL
            );
            CREATE INDEX idx_name_ngrams_gram ON name_ngrams(gram);
            CREATE INDEX idx_name_ngrams_symbol_id ON name_ngrams(symbol_id);
            """
        )
        rows = connection.execute("SELECT id, normalized_name FROM symbols")
        batch: list[tuple[str, int, str, int, int]] = []
        for symbol_id, normalized_name in rows:
            for gram, position in name_ngrams(str(normalized_name or "")):
                batch.append((gram, int(symbol_id), "name", position, 98 if china_hk else 95))
            if len(batch) >= 50_000:
                connection.executemany(
                    "INSERT INTO name_ngrams(gram,symbol_id,field_type,position,confidence) VALUES (?,?,?,?,?)",
                    batch,
                )
                batch.clear()
        if batch:
            connection.executemany(
                "INSERT INTO name_ngrams(gram,symbol_id,field_type,position,confidence) VALUES (?,?,?,?,?)",
                batch,
            )

        connection.execute("DROP TABLE IF EXISTS symbols_fts")
        if china_hk:
            connection.execute(
                "CREATE VIRTUAL TABLE symbols_fts USING fts5("
                "symbol,name,normalized_name,chinese_name,english_name,aliases,exchange,market,"
                "tokenize='unicode61',prefix='2 3 4')"
            )
            connection.execute(
                "INSERT INTO symbols_fts(rowid,symbol,name,normalized_name,chinese_name,english_name,aliases,exchange,market) "
                "SELECT s.id,s.symbol,s.name,s.normalized_name,s.chinese_name,s.english_name,"
                "COALESCE((SELECT group_concat(a.alias,' ') FROM aliases a WHERE a.symbol_id=s.id),''),"
                "s.exchange,s.market FROM symbols s"
            )
        else:
            connection.execute(
                "CREATE VIRTUAL TABLE symbols_fts USING fts5("
                "symbol,name,normalized_name,aliases,exchange,country,"
                "tokenize='unicode61',prefix='2 3 4')"
            )
            connection.execute(
                "INSERT INTO symbols_fts(rowid,symbol,name,normalized_name,aliases,exchange,country) "
                "SELECT s.id,s.symbol,s.name,s.normalized_name,"
                "COALESCE((SELECT group_concat(a.alias,' ') FROM aliases a WHERE a.symbol_id=s.id),''),"
                "s.exchange,s.country FROM symbols s"
            )
        connection.commit()
        if "metadata" in {
            str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master")
        }:
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key,value) VALUES ('schema_version','2')"
            )
            connection.commit()
        connection.execute("ANALYZE")
        connection.execute("VACUUM")
        count = int(connection.execute("SELECT COUNT(*) FROM name_ngrams").fetchone()[0])
        print(f"Upgraded {path}: ngrams={count}, size={path.stat().st_size / 1024 / 1024:.2f} MB")
    finally:
        connection.close()


def name_ngrams(value: str) -> list[tuple[str, int]]:
    compact = re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", value.casefold())
    sizes = (2, 3) if re.search(r"[\u3400-\u9fff]", compact) else (3,)
    result: list[tuple[str, int]] = []
    seen: set[str] = set()
    for size in sizes:
        for position in range(max(0, len(compact) - size + 1)):
            gram = compact[position : position + size]
            if gram and gram not in seen:
                seen.add(gram)
                result.append((gram, position))
    return result[:64]


if __name__ == "__main__":
    raise SystemExit(main())
