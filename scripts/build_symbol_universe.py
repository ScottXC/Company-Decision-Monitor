from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "src" / "cdm_desktop" / "resources" / "symbol_universe" / "symbol_universe.sqlite"

FIELDS = [
    "symbol",
    "name",
    "currency",
    "exchange",
    "mic",
    "market",
    "country",
    "sector",
    "industry",
    "instrument_type",
    "source",
    "normalized_symbol",
    "normalized_name",
    "aliases_json",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build bundled symbol universe index from FinanceDatabase.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--include-etf", action="store_true", help="Reserved for future ETF inclusion.")
    args = parser.parse_args()

    try:
        rows = _load_finance_database_equities()
    except Exception as exc:
        print(f"Failed to load FinanceDatabase equities: {exc}")
        print("Install build dependency with: python -m pip install 'FinanceDatabase>=2.4,<3'")
        return 1

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(".sqlite.tmp")
    if temp.exists():
        temp.unlink()

    generated_at = datetime.now(UTC).isoformat()
    package_version = _package_version("FinanceDatabase")
    count = _write_sqlite(temp, rows, generated_at, package_version)
    temp.replace(output)
    print(f"Symbol universe index: {output}")
    print(f"Records: {count}")
    print(f"Size: {output.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"Source: FinanceDatabase {package_version}")
    return 0


def _load_finance_database_equities() -> list[dict[str, Any]]:
    import financedatabase as fd  # type: ignore[import-not-found]

    frame = fd.Equities().select()
    records: list[dict[str, Any]] = []
    for symbol, row in frame.iterrows():
        data = row.to_dict()
        name = _clean_text(data.get("name"))
        symbol_text = _clean_text(symbol)
        if not symbol_text or not name:
            continue
        records.append(
            {
                "symbol": symbol_text,
                "name": name,
                "currency": _clean_text(data.get("currency")),
                "exchange": _clean_text(data.get("exchange")),
                "mic": _clean_text(data.get("mic")),
                "market": _clean_text(data.get("market")),
                "country": _clean_text(data.get("country")),
                "sector": _clean_text(data.get("sector")),
                "industry": _clean_text(data.get("industry")),
                "instrument_type": "equity",
                "source": "FinanceDatabase",
                "normalized_symbol": _normalize_symbol(symbol_text),
                "normalized_name": _normalize_name(name),
                "aliases_json": json.dumps(_aliases(symbol_text, name), ensure_ascii=False),
            }
        )
    return records


def _write_sqlite(path: Path, rows: list[dict[str, Any]], generated_at: str, package_version: str) -> int:
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute(
            """
            CREATE TABLE symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                currency TEXT,
                exchange TEXT,
                mic TEXT,
                market TEXT,
                country TEXT,
                sector TEXT,
                industry TEXT,
                instrument_type TEXT,
                source TEXT,
                normalized_symbol TEXT,
                normalized_name TEXT,
                aliases_json TEXT
            )
            """
        )
        conn.execute("CREATE INDEX idx_symbols_normalized_symbol ON symbols(normalized_symbol)")
        conn.execute("CREATE INDEX idx_symbols_normalized_name ON symbols(normalized_name)")
        conn.execute("CREATE INDEX idx_symbols_exchange ON symbols(exchange)")
        conn.execute("CREATE INDEX idx_symbols_country ON symbols(country)")
        conn.executemany(
            f"INSERT INTO symbols ({', '.join(FIELDS)}) VALUES ({', '.join(['?'] * len(FIELDS))})",
            [[row.get(field, "") for field in FIELDS] for row in rows],
        )
        conn.execute(
            """
            CREATE TABLE aliases (
                symbol_id INTEGER NOT NULL,
                alias TEXT NOT NULL,
                normalized_alias TEXT NOT NULL,
                alias_type TEXT NOT NULL,
                FOREIGN KEY(symbol_id) REFERENCES symbols(id)
            )
            """
        )
        alias_rows: list[tuple[int, str, str, str]] = []
        for symbol_id, row in enumerate(rows, start=1):
            aliases = _decode_aliases(row.get("aliases_json"))
            aliases.extend([str(row.get("symbol") or ""), str(row.get("name") or "")])
            seen: set[str] = set()
            for alias in aliases:
                normalized_alias = _normalize_name(alias)
                if not normalized_alias or normalized_alias in seen:
                    continue
                seen.add(normalized_alias)
                alias_type = "symbol" if _normalize_symbol(alias) == row.get("normalized_symbol") else "name"
                alias_rows.append((symbol_id, alias, normalized_alias, alias_type))
        conn.executemany(
            "INSERT INTO aliases (symbol_id, alias, normalized_alias, alias_type) VALUES (?, ?, ?, ?)",
            alias_rows,
        )
        conn.execute("CREATE INDEX idx_aliases_normalized_alias ON aliases(normalized_alias)")
        conn.execute("CREATE INDEX idx_aliases_symbol_id ON aliases(symbol_id)")
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE symbols_fts USING fts5("
                "symbol, name, normalized_name, aliases, exchange, country, "
                "tokenize='unicode61', prefix='2 3 4')"
            )
            fts_rows = [
                (
                    str(row.get("symbol") or ""),
                    str(row.get("name") or ""),
                    str(row.get("normalized_name") or ""),
                    " ".join(_decode_aliases(row.get("aliases_json"))),
                    str(row.get("exchange") or ""),
                    str(row.get("country") or ""),
                )
                for row in rows
            ]
            conn.executemany(
                "INSERT INTO symbols_fts(symbol,name,normalized_name,aliases,exchange,country) "
                "VALUES (?,?,?,?,?,?)",
                fts_rows,
            )
        except sqlite3.OperationalError:
            # FTS5 is an optimization only; indexed exact/prefix search remains available.
            pass
        conn.execute(
            "CREATE TABLE name_ngrams (gram TEXT NOT NULL, symbol_id INTEGER NOT NULL, "
            "field_type TEXT NOT NULL, position INTEGER NOT NULL, confidence INTEGER NOT NULL)"
        )
        conn.executemany(
            "INSERT INTO name_ngrams(gram,symbol_id,field_type,position,confidence) VALUES (?,?,?,?,?)",
            (
                (gram, symbol_id, "name", position, 95)
                for symbol_id, row in enumerate(rows, start=1)
                for gram, position in _name_ngrams(str(row.get("normalized_name") or ""))
            ),
        )
        conn.execute("CREATE INDEX idx_name_ngrams_gram ON name_ngrams(gram)")
        conn.execute("CREATE INDEX idx_name_ngrams_symbol_id ON name_ngrams(symbol_id)")
        conn.execute("CREATE VIEW symbol_universe AS SELECT * FROM symbols")
        metadata_payload = {
            "schema_version": 2,
            "source": "FinanceDatabase",
            "generated_at": generated_at,
            "record_count": len(rows),
            "fields": FIELDS,
            "license": "MIT",
            "package_version": package_version,
            "instrument_scope": "equities",
            "is_realtime": False,
        }
        conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        for key, value in metadata_payload.items():
            conn.execute("INSERT INTO metadata (key, value) VALUES (?, ?)", (key, json.dumps(value, ensure_ascii=False)))
        conn.commit()
        conn.execute("ANALYZE")
        conn.commit()
        conn.execute("VACUUM")
    finally:
        conn.close()
    return len(rows)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none"} else text


def _normalize_symbol(value: str) -> str:
    return value.strip().upper().replace("-", ".")


def _normalize_name(value: str) -> str:
    cleaned = value
    try:
        from cleanco import basename as cleanco_basename

        cleaned = cleanco_basename(value)
    except Exception:  # noqa: BLE001
        cleaned = value
    return " ".join(cleaned.casefold().replace(",", " ").split())


def _name_ngrams(value: str) -> list[tuple[str, int]]:
    compact = re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", value.casefold())
    if not compact:
        return []
    sizes = (2, 3) if re.search(r"[\u3400-\u9fff]", compact) else (3,)
    result: list[tuple[str, int]] = []
    seen: set[str] = set()
    for size in sizes:
        for position in range(max(0, len(compact) - size + 1)):
            gram = compact[position : position + size]
            if gram not in seen:
                seen.add(gram)
                result.append((gram, position))
    return result[:64]


def _aliases(symbol: str, name: str) -> list[str]:
    aliases = {symbol, _normalize_symbol(symbol)}
    base_symbol = symbol.split(".", 1)[0]
    if base_symbol:
        aliases.add(base_symbol)
    short = name.replace(",", " ").split("  ", 1)[0].strip()
    if short:
        aliases.add(short)
    return sorted(item for item in aliases if item)


def _decode_aliases(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not value:
        return []
    try:
        decoded = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return [str(item).strip() for item in decoded if str(item).strip()] if isinstance(decoded, list) else []


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "unknown"


if __name__ == "__main__":
    sys.exit(main())
