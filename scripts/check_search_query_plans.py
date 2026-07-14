from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "src" / "cdm_desktop" / "resources" / "symbol_universe" / "symbol_universe.sqlite"
REPORT = ROOT / "reports" / "search_query_plan_report.md"

QUERIES = {
    "exact symbol": ("SELECT id FROM symbols WHERE normalized_symbol=? LIMIT 10", ("AAPL",)),
    "exact alias": (
        "SELECT s.id FROM aliases a JOIN symbols s ON s.id=a.symbol_id WHERE a.normalized_alias=? LIMIT 10",
        ("sample",),
    ),
    "name prefix": (
        "SELECT id FROM symbols WHERE normalized_name>=? AND normalized_name<? LIMIT 30",
        ("sample", "sample\uffff"),
    ),
    "alias prefix": (
        "SELECT s.id FROM aliases a JOIN symbols s ON s.id=a.symbol_id "
        "WHERE a.normalized_alias>=? AND a.normalized_alias<? LIMIT 30",
        ("sample", "sample\uffff"),
    ),
    "FTS": ("SELECT rowid FROM symbols_fts WHERE symbols_fts MATCH ? LIMIT 30", ('"sample"*',)),
    "English multi-word FTS": (
        "SELECT rowid FROM symbols_fts WHERE symbols_fts MATCH ? LIMIT 30",
        ('"international"* AND "business"*',),
    ),
    "Chinese n-gram": (
        "SELECT symbol_id,COUNT(DISTINCT gram) FROM name_ngrams WHERE gram IN (?,?) "
        "GROUP BY symbol_id ORDER BY COUNT(DISTINCT gram) DESC LIMIT 30",
        ("贵州", "州茅"),
    ),
}


def main() -> int:
    connection = sqlite3.connect(f"{INDEX.resolve().as_uri()}?mode=ro", uri=True)
    lines = ["# Search Query Plan Report", ""]
    failures: list[str] = []
    try:
        for name, (sql, parameters) in QUERIES.items():
            rows = [str(row[3]) for row in connection.execute("EXPLAIN QUERY PLAN " + sql, parameters)]
            plan = " | ".join(rows)
            lines.extend([f"## {name}", f"`{plan}`", ""])
            upper = plan.upper()
            indexed = "INDEX" in upper or "USING INTEGER PRIMARY KEY" in upper
            if name not in {"FTS", "English multi-word FTS", "Chinese n-gram"} and not indexed:
                failures.append(f"{name}: indexed lookup was not selected")
            if name == "Chinese n-gram" and "IDX_NAME_NGRAMS_GRAM" not in upper:
                failures.append(f"{name}: n-gram index was not selected")
            if "%" in sql or "ALIASES_JSON" in sql.upper():
                failures.append(f"{name}: wildcard or aliases_json scan detected")
            if "LIMIT" not in sql.upper():
                failures.append(f"{name}: LIMIT missing")
        provider_source = (
            ROOT / "src" / "cdm_desktop" / "public_api" / "providers.py"
        ).read_text(encoding="utf-8")
        provider_block = provider_source[
            provider_source.index("class SymbolUniverseProvider") :
            provider_source.index("class FinanceDatabaseProvider")
        ]
        if "aliases_json LIKE" in provider_block or 'f"%{term}%"' in provider_block:
            failures.append("production provider contains a leading-wildcard alias/name scan")
        if "FUZZY_SHORTLIST_LIMIT = 100" not in provider_block:
            failures.append("production fuzzy shortlist is not bounded to 100")
    finally:
        connection.close()
    lines.extend(["## Result", "PASS" if not failures else "FAIL", *[f"- {item}" for item in failures]])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
