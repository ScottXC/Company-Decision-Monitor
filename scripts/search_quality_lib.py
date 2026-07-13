from __future__ import annotations

# ruff: noqa: E402
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SEARCH_CASES_PATH = ROOT / "tests" / "fixtures" / "search_quality_cases.json"
NEWS_CASES_PATH = ROOT / "tests" / "fixtures" / "news_quality_cases.json"

from cdm_desktop.public_api.models import CompanyResult
from cdm_desktop.public_api.query import analyze_query, normalize_cn_symbol, normalize_hk_symbol
from cdm_desktop.public_api.ranking import group_companies, rank_and_dedupe_companies
from cdm_desktop.public_api.seed_aliases import seed_aliases_for_query


def load_search_cases() -> list[dict[str, Any]]:
    return json.loads(SEARCH_CASES_PATH.read_text(encoding="utf-8"))


def load_news_cases() -> list[dict[str, Any]]:
    return json.loads(NEWS_CASES_PATH.read_text(encoding="utf-8"))


def offline_search(query: str) -> tuple[list[CompanyResult], dict[str, Any]]:
    query_info = analyze_query(query)
    cases = _matching_cases(query)
    candidates: list[CompanyResult] = []
    for case in cases:
        candidates.extend(_case_candidates(case))
    ranked = rank_and_dedupe_companies(candidates, query_info)
    diagnostics = {
        "raw_query": query,
        "normalized_query": query_info.normalized,
        "detected_query_type": query_info.kind,
        "market_hint": query_info.market_hint,
        "symbol": query_info.symbol,
        "query_variants": list(query_info.variants),
        "seed_aliases_used": seed_aliases_for_query(set(query_info.variants) | {query}),
        "dedup_before_count": len(candidates),
        "dedup_after_count": len(ranked),
        "grouped_counts": {key: len(value) for key, value in group_companies(ranked).items()},
    }
    return ranked, diagnostics


def case_hit(results: list[CompanyResult], case: dict[str, Any], *, at: int = 3) -> bool:
    expected_symbols = {_canonical_symbol(symbol) for symbol in case.get("expected_symbols", [])}
    expected_names = {str(name).casefold() for name in case.get("expected_names", [])}
    for result in results[:at]:
        result_symbols = {
            _canonical_symbol(result.symbol),
            *(_canonical_symbol(alias) for alias in result.aliases),
        }
        result_names = {
            result.name.casefold(),
            result.display_name.casefold(),
            result.legal_name.casefold(),
            *(alias.casefold() for alias in result.aliases),
        }
        if expected_symbols & result_symbols:
            return True
        if any(expected in name or name in expected for expected in expected_names for name in result_names if name):
            return True
    return False


def _matching_cases(query: str) -> list[dict[str, Any]]:
    info = analyze_query(query)
    terms = {_normalize(term) for term in (query, info.symbol, *info.variants) if term}
    matches = []
    for case in load_search_cases():
        case_terms = {
            _normalize(case.get("query", "")),
            *(_normalize(symbol) for symbol in case.get("expected_symbols", [])),
            *(_normalize(name) for name in case.get("expected_names", [])),
            *(_normalize(alias) for alias in case.get("expected_aliases", [])),
        }
        if terms & case_terms:
            matches.append(case)
    return matches[:4]


def _case_candidates(case: dict[str, Any]) -> list[CompanyResult]:
    symbols = [str(item) for item in case.get("expected_symbols", []) if item]
    names = [str(item) for item in case.get("expected_names", []) if item]
    aliases = [str(item) for item in case.get("expected_aliases", []) if item]
    markets = [str(item) for item in case.get("expected_markets", []) if item]
    primary_symbol = _preferred_symbol(symbols)
    market, exchange = _market_exchange(primary_symbol, markets)
    name = names[0] if names else primary_symbol or str(case.get("query") or "")
    primary = CompanyResult(
        name=name,
        display_name=name,
        symbol=primary_symbol,
        exchange=exchange,
        market=market,
        country=_country_for_market(market),
        aliases=sorted({*symbols, *names[1:], *aliases} - {name, primary_symbol, ""}),
        category="financial",
        provider="Search quality fixture",
        provider_id="fmp" if market != "US directory" else "nasdaq_directory",
        source_url="fixture://search-quality",
        match_reason="Search quality fixture candidate",
        match_score=65,
        raw={"fixture": "search_quality_cases"},
    )
    weak = CompanyResult(
        name=f"{name} related entity",
        display_name=f"{name} related entity",
        category="global",
        provider="Wikidata / Wikipedia",
        provider_id="wikidata",
        wikidata_id=f"QFIXTURE{sum(ord(ch) for ch in name) % 100000}",
        source_url="fixture://weak-related",
        match_reason="Weak encyclopedia fixture candidate",
        match_score=45,
    )
    return [primary, weak]


def _preferred_symbol(symbols: list[str]) -> str:
    if not symbols:
        return ""
    for symbol in symbols:
        normalized = _canonical_symbol(symbol)
        if normalized.startswith(("HK", "SH", "SZ")) or normalized in {"BRK.B", "BRK-B"}:
            return normalized
    return _canonical_symbol(symbols[0])


def _canonical_symbol(value: str) -> str:
    cleaned = str(value or "").strip().upper().replace("-", ".")
    if not cleaned:
        return ""
    if cleaned.startswith("HK") or (cleaned.isdigit() and len(cleaned) <= 5):
        return normalize_hk_symbol(cleaned)
    if cleaned.startswith(("SH", "SZ")) or (cleaned.isdigit() and len(cleaned) == 6):
        return normalize_cn_symbol(cleaned)
    return cleaned


def _market_exchange(symbol: str, markets: list[str]) -> tuple[str, str]:
    if symbol.startswith("HK"):
        return "HK", "HKEX"
    if symbol.startswith("SH"):
        return "CN", "SSE"
    if symbol.startswith("SZ"):
        return "CN", "SZSE"
    if markets:
        return markets[0], markets[0]
    return "US", "NASDAQ"


def _country_for_market(market: str) -> str:
    return {"HK": "Hong Kong", "CN": "China", "US": "United States"}.get(market, market)


def _normalize(value: str) -> str:
    return str(value or "").strip().casefold().replace(" ", "").replace("-", ".")
