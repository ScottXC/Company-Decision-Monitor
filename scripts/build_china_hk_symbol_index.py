from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cdm_desktop.public_api.china_hk_index import (  # noqa: E402
    CHINA_HK_INDEX_PATH,
    CHINA_HK_INDEX_SCHEMA_VERSION,
    normalize_china_hk_symbol,
    normalized_local_name,
)

GLOBAL_INDEX = ROOT / "src" / "cdm_desktop" / "resources" / "symbol_universe" / "symbol_universe.sqlite"
CORE_SYMBOLS = {
    "SH600519",
    "SZ002594",
    "SH601318",
    "SZ300750",
    "HK00700",
    "HK09988",
    "HK03690",
    "HK01810",
    "HK09618",
    "HK01024",
    "HK00005",
}
CORE_HK_SYMBOLS = {symbol for symbol in CORE_SYMBOLS if symbol.startswith("HK")}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the bundled China/HK symbol index.")
    parser.add_argument("--output", type=Path, default=CHINA_HK_INDEX_PATH)
    parser.add_argument("--use-existing", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    temporary = output.with_suffix(".tmp.sqlite")
    if args.use_existing and output.exists():
        _validate_existing(output)
        print(f"Using verified existing China/HK index: {output}")
        return 0

    generated_at = datetime.now(UTC).isoformat()
    records: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    if temporary.exists():
        records.update(_load_partial_records(temporary))
        print(f"Resuming verified-source partial index: {len(records)} records")
    akshare_version = "unavailable"
    try:
        import akshare as ak

        akshare_version = str(getattr(ak, "__version__", "unknown"))
        for loader, market in (() if records else (
            ("stock_info_sh_name_code", "SH"),
            ("stock_info_sz_name_code", "SZ"),
            ("stock_info_bj_name_code", "BJ"),
            ("stock_hk_spot_em", "HK"),
        )):
            try:
                frame = getattr(ak, loader)()
                _merge_akshare_rows(records, frame.to_dict(orient="records"), market, generated_at)
                print(f"AKShare {market}: {len(frame)} records")
            except Exception as exc:  # noqa: BLE001
                warning = f"AKShare {market} source unavailable: {type(exc).__name__}"
                warnings.append(warning)
                print(f"WARNING: {warning}")
        _merge_core_hk_profiles(records, ak, generated_at, warnings)
    except ImportError as exc:
        raise RuntimeError("AKShare is required to build the China/HK index.") from exc

    if not records:
        try:
            import financedatabase as fd

            fresh_count = _merge_finance_database_rows(
                records,
                fd.Equities().select().reset_index().to_dict(orient="records"),
                generated_at,
            )
            print(f"FinanceDatabase current equities fallback: {fresh_count} records")
        except Exception as exc:  # noqa: BLE001
            warning = f"FinanceDatabase current dataset unavailable: {type(exc).__name__}"
            warnings.append(warning)
            print(f"WARNING: {warning}")
    fallback_count = _merge_global_fallback(records, generated_at)
    print(f"Bundled global-index fallback: {fallback_count} records")
    if not records:
        raise RuntimeError("No real China/HK source returned records; refusing to create an empty index.")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary.unlink(missing_ok=True)
    _write_database(temporary, records.values(), generated_at, akshare_version, warnings)
    _validate_existing(temporary)
    output.unlink(missing_ok=True)
    temporary.replace(output)
    size_mb = output.stat().st_size / 1024 / 1024
    print(f"China/HK index: {output}")
    print(f"Records: {len(records)}, size: {size_mb:.2f} MB, AKShare: {akshare_version}")
    return 0


def _load_partial_records(path: Path) -> dict[str, dict[str, Any]]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "symbols" not in tables:
            return {}
        return {str(row["symbol"]): dict(row) for row in connection.execute("SELECT * FROM symbols")}
    except sqlite3.DatabaseError:
        return {}
    finally:
        connection.close()


def _merge_akshare_rows(
    target: dict[str, dict[str, Any]], rows: list[dict[str, Any]], market: str, generated_at: str
) -> None:
    for row in rows:
        code = _first(row, "证券代码", "A股代码", "代码", "symbol")
        name = _first(row, "证券简称", "A股简称", "名称", "name")
        if not code or not name:
            continue
        symbol = normalize_china_hk_symbol(code, market)
        long_name = _first(row, "公司全称", "证券全称", "英文名称")
        record = {
            "symbol": symbol,
            "normalized_symbol": symbol,
            "display_symbol": symbol,
            "chinese_name": name,
            "english_name": _first(row, "英文名称"),
            "name": long_name or name,
            "long_name": long_name,
            "short_name": _first(row, "公司简称", "A股简称", "证券简称") or name,
            "exchange": {"SH": "SSE", "SZ": "SZSE", "BJ": "BSE", "HK": "HKEX"}[market],
            "market": market,
            "board": _first(row, "板块"),
            "country": "China" if market != "HK" else "Hong Kong",
            "currency": "CNY" if market != "HK" else "HKD",
            "industry": _first(row, "所属行业", "行业"),
            "region": _first(row, "地区", "地域"),
            "listing_date": _first(row, "上市日期", "A股上市日期"),
            "instrument_type": "equity",
            "source": "AKShare",
            "source_detail": f"AKShare {market} public symbol list",
            "generated_at": generated_at,
        }
        target[symbol] = record


def _merge_core_hk_profiles(
    target: dict[str, dict[str, Any]], ak: Any, generated_at: str, warnings: list[str]
) -> None:
    for symbol in sorted(CORE_HK_SYMBOLS - target.keys()):
        code = symbol[2:]
        try:
            company_rows = ak.stock_hk_company_profile_em(symbol=code).to_dict(orient="records")
            security_rows = ak.stock_hk_security_profile_em(symbol=code).to_dict(orient="records")
            company = company_rows[0] if company_rows else {}
            security = security_rows[0] if security_rows else {}
            name = _first(company, "公司名称") or _first(security, "证券简称")
            if not name:
                raise ValueError("empty company/security profile")
            target[symbol] = {
                "symbol": symbol,
                "normalized_symbol": symbol,
                "display_symbol": symbol,
                "chinese_name": name,
                "english_name": _first(company, "英文名称"),
                "name": name,
                "long_name": name,
                "short_name": _first(security, "证券简称") or name,
                "exchange": "HKEX",
                "market": "HK",
                "board": _first(security, "板块"),
                "country": _first(company, "注册地") or "Hong Kong",
                "currency": "HKD",
                "industry": _first(company, "所属行业"),
                "region": _first(company, "注册地"),
                "listing_date": _first(security, "上市日期"),
                "instrument_type": "equity",
                "source": "AKShare",
                "source_detail": "AKShare HK public security/company profile",
                "generated_at": generated_at,
            }
            print(f"AKShare HK profile fallback: {symbol}")
        except Exception as exc:  # noqa: BLE001
            warning = f"AKShare HK profile {symbol} unavailable: {type(exc).__name__}"
            warnings.append(warning)
            print(f"WARNING: {warning}")


def _merge_global_fallback(target: dict[str, dict[str, Any]], generated_at: str) -> int:
    if not GLOBAL_INDEX.exists():
        return 0
    connection = sqlite3.connect(GLOBAL_INDEX)
    connection.row_factory = sqlite3.Row
    count = 0
    try:
        rows = connection.execute(
            """
            SELECT symbol, name, exchange, market, country, currency, sector, industry, instrument_type
            FROM symbols
            WHERE exchange IN ('SHH', 'SHZ', 'HKG') AND instrument_type = 'equity'
            """
        )
        for raw in rows:
            row = dict(raw)
            symbol = _global_symbol(row["symbol"], row["exchange"])
            if not symbol or symbol in target:
                continue
            target[symbol] = {
                "symbol": symbol,
                "normalized_symbol": symbol,
                "display_symbol": symbol,
                "chinese_name": "",
                "english_name": row["name"] or "",
                "name": row["name"] or symbol,
                "long_name": row["name"] or "",
                "short_name": "",
                "exchange": {"SHH": "SSE", "SHZ": "SZSE", "HKG": "HKEX"}[row["exchange"]],
                "market": {"SHH": "SH", "SHZ": "SZ", "HKG": "HK"}[row["exchange"]],
                "board": "",
                "country": row["country"] or ("Hong Kong" if row["exchange"] == "HKG" else "China"),
                "currency": row["currency"] or "",
                "industry": row["industry"] or "",
                "sector": row["sector"] or "",
                "region": "",
                "listing_date": "",
                "instrument_type": row["instrument_type"] or "equity",
                "source": "FinanceDatabase",
                "source_detail": "Bundled global symbol-universe fallback",
                "generated_at": generated_at,
            }
            count += 1
    finally:
        connection.close()
    return count


def _merge_finance_database_rows(
    target: dict[str, dict[str, Any]], rows: list[dict[str, Any]], generated_at: str
) -> int:
    count = 0
    for row in rows:
        exchange = str(row.get("exchange") or "")
        if exchange not in {"SHH", "SHZ", "HKG"} or bool(row.get("delisted")):
            continue
        symbol = _global_symbol(str(row.get("symbol") or ""), exchange)
        name = _first(row, "name")
        if not symbol or not name or symbol in target:
            continue
        target[symbol] = {
            "symbol": symbol,
            "normalized_symbol": symbol,
            "display_symbol": symbol,
            "chinese_name": "",
            "english_name": name,
            "name": name,
            "long_name": name,
            "short_name": "",
            "exchange": {"SHH": "SSE", "SHZ": "SZSE", "HKG": "HKEX"}[exchange],
            "market": {"SHH": "SH", "SHZ": "SZ", "HKG": "HK"}[exchange],
            "board": "",
            "country": _first(row, "country") or ("Hong Kong" if exchange == "HKG" else "China"),
            "currency": _first(row, "currency"),
            "sector": _first(row, "sector"),
            "industry": _first(row, "industry"),
            "region": _first(row, "state"),
            "listing_date": "",
            "instrument_type": "equity",
            "source": "FinanceDatabase",
            "source_detail": "FinanceDatabase current equities dataset",
            "generated_at": generated_at,
        }
        count += 1
    return count


def _global_symbol(value: str, exchange: str) -> str:
    raw = str(value or "").upper()
    code = raw.split(".", 1)[0]
    if exchange == "HKG":
        return normalize_china_hk_symbol(code, "HK")
    if exchange == "SHH":
        return normalize_china_hk_symbol(code, "SH")
    if exchange == "SHZ":
        return normalize_china_hk_symbol(code, "SZ")
    return ""


def _write_database(
    path: Path,
    records: Any,
    generated_at: str,
    akshare_version: str,
    warnings: list[str],
) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE symbols (
                id INTEGER PRIMARY KEY, symbol TEXT NOT NULL UNIQUE, normalized_symbol TEXT NOT NULL,
                display_symbol TEXT NOT NULL, name TEXT NOT NULL, normalized_name TEXT NOT NULL,
                chinese_name TEXT, english_name TEXT, long_name TEXT, short_name TEXT,
                exchange TEXT, market TEXT, board TEXT, country TEXT, currency TEXT,
                sector TEXT, industry TEXT, region TEXT, listing_date TEXT,
                instrument_type TEXT, source TEXT NOT NULL, source_detail TEXT, generated_at TEXT
            );
            CREATE TABLE aliases (
                symbol_id INTEGER NOT NULL, alias TEXT NOT NULL, normalized_alias TEXT NOT NULL,
                alias_type TEXT NOT NULL, language TEXT, confidence INTEGER NOT NULL,
                UNIQUE(symbol_id, normalized_alias), FOREIGN KEY(symbol_id) REFERENCES symbols(id)
            );
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE INDEX idx_china_hk_symbol ON symbols(normalized_symbol);
            CREATE INDEX idx_china_hk_name ON symbols(normalized_name);
            CREATE INDEX idx_china_hk_market ON symbols(market);
            CREATE INDEX idx_china_hk_exchange ON symbols(exchange);
            CREATE INDEX idx_china_hk_industry ON symbols(industry);
            CREATE INDEX idx_china_hk_alias ON aliases(normalized_alias);
            CREATE TABLE name_ngrams (
                gram TEXT NOT NULL, symbol_id INTEGER NOT NULL, field_type TEXT NOT NULL,
                position INTEGER NOT NULL, confidence INTEGER NOT NULL
            );
            CREATE INDEX idx_name_ngrams_gram ON name_ngrams(gram);
            CREATE INDEX idx_name_ngrams_symbol_id ON name_ngrams(symbol_id);
            """
        )
        try:
            connection.execute(
                "CREATE VIRTUAL TABLE symbols_fts USING fts5("
                "symbol,name,normalized_name,chinese_name,english_name,aliases,exchange,market,"
                "tokenize='unicode61',prefix='2 3 4')"
            )
            has_fts = True
        except sqlite3.OperationalError:
            has_fts = False
        counts = {"SH": 0, "SZ": 0, "BJ": 0, "HK": 0}
        alias_count = 0
        for record in sorted(records, key=lambda item: item["symbol"]):
            name = record.get("name") or record["symbol"]
            values = (
                record["symbol"], record["normalized_symbol"], record["display_symbol"], name,
                normalized_local_name(name), record.get("chinese_name", ""), record.get("english_name", ""),
                record.get("long_name", ""), record.get("short_name", ""), record.get("exchange", ""),
                record.get("market", ""), record.get("board", ""), record.get("country", ""),
                record.get("currency", ""), record.get("sector", ""), record.get("industry", ""),
                record.get("region", ""), record.get("listing_date", ""), record.get("instrument_type", "equity"),
                record["source"], record.get("source_detail", ""), generated_at,
            )
            cursor = connection.execute(
                "INSERT INTO symbols(symbol,normalized_symbol,display_symbol,name,normalized_name,chinese_name,english_name,long_name,short_name,exchange,market,board,country,currency,sector,industry,region,listing_date,instrument_type,source,source_detail,generated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                values,
            )
            symbol_id = int(cursor.lastrowid)
            aliases = _aliases(record)
            for alias, alias_type, language, confidence in aliases:
                normalized = normalized_local_name(alias)
                if not normalized:
                    continue
                connection.execute(
                    "INSERT OR IGNORE INTO aliases(symbol_id,alias,normalized_alias,alias_type,language,confidence) VALUES (?,?,?,?,?,?)",
                    (symbol_id, alias, normalized, alias_type, language, confidence),
                )
                alias_count += 1
            if has_fts:
                connection.execute(
                    "INSERT INTO symbols_fts(rowid,symbol,name,normalized_name,chinese_name,english_name,aliases,exchange,market) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (symbol_id, record["symbol"], name, normalized_local_name(name), record.get("chinese_name", ""), record.get("english_name", ""), " ".join(a[0] for a in aliases), record.get("exchange", ""), record.get("market", "")),
                )
            connection.executemany(
                "INSERT INTO name_ngrams(gram,symbol_id,field_type,position,confidence) VALUES (?,?,?,?,?)",
                [
                    (gram, symbol_id, "name", position, 98)
                    for gram, position in _name_ngrams(normalized_local_name(name))
                ],
            )
            counts[record.get("market", "")] = counts.get(record.get("market", ""), 0) + 1
        metadata = {
            "schema_version": str(CHINA_HK_INDEX_SCHEMA_VERSION),
            "source": "AKShare public symbol lists with FinanceDatabase fallback",
            "akshare_version": akshare_version,
            "generated_at": generated_at,
            "a_share_record_count": str(counts["SH"] + counts["SZ"] + counts["BJ"]),
            "hk_share_record_count": str(counts["HK"]),
            "alias_count": str(alias_count),
            "record_count": str(sum(counts.values())),
            "fts5": str(has_fts).lower(),
            "warnings": json.dumps(warnings, ensure_ascii=False),
        }
        connection.executemany("INSERT INTO metadata(key,value) VALUES (?,?)", metadata.items())
        connection.commit()
        connection.execute("ANALYZE")
        connection.execute("VACUUM")
    finally:
        connection.close()


def _aliases(record: dict[str, Any]) -> list[tuple[str, str, str, int]]:
    candidates = [
        (record["symbol"], "symbol", "und", 100),
        (record["symbol"][2:], "raw_symbol", "und", 98),
        (record.get("chinese_name", ""), "company_name", "zh", 98),
        (record.get("short_name", ""), "short_name", "zh", 96),
        (record.get("english_name", ""), "company_name", "en", 95),
        (record.get("long_name", ""), "legal_name", "und", 94),
    ]
    seen: set[str] = set()
    result = []
    for alias, kind, language, confidence in candidates:
        normalized = normalized_local_name(alias)
        if alias and normalized not in seen:
            seen.add(normalized)
            result.append((str(alias), kind, language, confidence))
    return result


def _name_ngrams(value: str) -> list[tuple[str, int]]:
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


def _validate_existing(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        if not {"symbols", "aliases", "metadata"}.issubset(tables):
            raise RuntimeError("China/HK index schema is incomplete.")
        count = int(connection.execute("SELECT count(*) FROM symbols").fetchone()[0])
        if count < 1000:
            raise RuntimeError(f"China/HK index has an implausible record count: {count}")
        placeholders = ",".join("?" for _ in CORE_SYMBOLS)
        present = {
            row[0]
            for row in connection.execute(
                f"SELECT symbol FROM symbols WHERE symbol IN ({placeholders})",
                tuple(CORE_SYMBOLS),
            )
        }
        missing = sorted(CORE_SYMBOLS - present)
        if missing:
            raise RuntimeError(f"China/HK index is missing core securities: {', '.join(missing)}")
    finally:
        connection.close()


def _first(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() not in {"", "nan", "None"}:
            return str(value).strip()
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
