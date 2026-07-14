from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import replace
from difflib import SequenceMatcher

from cdm_desktop.public_api.models import CompanyResult
from cdm_desktop.public_api.query import QueryInfo, acronym, fuzzy_score, remove_company_suffix
from cdm_desktop.public_api.seed_aliases import matching_seed_aliases

PROVIDER_AUTHORITY = {
    "china_hk_symbol_index": 93,
    "symbol_universe": 91,
    "fmp": 96,
    "alpha_vantage": 94,
    "nasdaq_directory": 90,
    "gleif": 82,
    "companies_house": 80,
    "norway_brreg": 78,
    "opencorporates": 76,
    "wikidata": 64,
}

LISTED_PROVIDERS = {"china_hk_symbol_index", "symbol_universe", "fmp", "alpha_vantage", "nasdaq_directory"}
LEGAL_PROVIDERS = {"gleif", "opencorporates", "companies_house", "norway_brreg"}


def rank_and_dedupe_companies(companies: list[CompanyResult], query: QueryInfo) -> list[CompanyResult]:
    merged: dict[str, CompanyResult] = {}
    for company in companies:
        scored = score_company(company, query)
        key = canonical_company_key(scored)
        existing = merged.get(key)
        merged[key] = _merge_company(existing, scored) if existing else scored
    ranked = sorted(merged.values(), key=_sort_tuple, reverse=True)
    return ranked


def score_company(company: CompanyResult, query: QueryInfo) -> CompanyResult:
    candidate_terms = candidate_match_terms(company)
    normalized_terms = {remove_company_suffix(term) for term in candidate_terms if term}
    query_terms = set(query.variants) | {query.original, query.normalized, query.normalized_no_suffix, query.upper, query.symbol}
    query_terms = {term for term in query_terms if term}
    provider_score = PROVIDER_AUTHORITY.get(company.provider_id, 50)
    score = max(company.match_score, 0)
    reason = company.match_reason or "provider match"

    candidate_symbols = {_normalize_symbol(company.symbol)} - {""}
    direct_symbol_terms = {query.original, query.upper, query.symbol} if query.kind != "name" else set()
    query_symbols = {symbol for symbol in (_normalize_symbol(term) for term in direct_symbol_terms) if symbol}
    seed_matches = matching_seed_aliases({query.original, query.normalized, query.normalized_no_suffix})
    seed_company_match = any(_company_matches_seed(company, seed) for seed in seed_matches)
    seed_symbol_collision = any(
        _normalize_symbol(company.symbol) in {_normalize_symbol(symbol) for symbol in seed.symbols}
        for seed in seed_matches
        if company.symbol
    )

    if company.lei and query.kind == "lei" and company.lei.upper() == query.upper:
        score = 100
        reason = "LEI 完全匹配"
    elif candidate_symbols & query_symbols:
        score = 100
        reason = "代码完全匹配"
    elif any(remove_company_suffix(term) == query.normalized_no_suffix for term in normalized_terms):
        score = max(score, 95)
        reason = "公司名称完全匹配"
    elif seed_company_match:
        score = max(score, 93)
        reason = "高置信别名匹配"
    elif _acronym_exact(query_terms, candidate_terms):
        score = max(score, 90)
        reason = "缩写完全匹配"
    else:
        fuzzy = max((fuzzy_score(term, candidate) for term in query_terms for candidate in candidate_terms), default=0)
        if fuzzy >= 90:
            score = max(score, 80)
            reason = "强模糊匹配"
        elif fuzzy >= 75:
            score = max(score, 70)
            reason = "模糊匹配"
        elif fuzzy >= 60:
            score = max(score, 55)
            reason = "弱相关匹配"

    score += min(8, max(0, provider_score - 70) // 5)
    if company.symbol and company.exchange:
        score += 4
    if not any([company.symbol, company.lei, company.wikidata_id, company.company_number, company.source_url]):
        score -= 10
    if _is_fund_like(company) and query.kind == "name":
        score -= 15
    if company.provider_id == "wikidata" and query.symbol:
        score -= 12
    if seed_symbol_collision and not seed_company_match and query.kind == "name":
        score -= 30
    score = max(0, min(score, 100))

    result = replace(company)
    result.match_score = score
    result.match_reason = reason
    result.raw = {**company.raw, "ranking_provider_authority": provider_score}
    return result


def _company_matches_seed(company: CompanyResult, seed) -> bool:
    company_names = [company.name, company.display_name, company.legal_name]
    seed_names = [seed.canonical_name, *seed.aliases]
    return any(
        fuzzy_score(company_name, seed_name) >= 80
        for company_name in company_names
        if company_name
        for seed_name in seed_names
        if seed_name
    )


def group_companies(companies: list[CompanyResult]) -> dict[str, list[CompanyResult]]:
    best = [item for item in companies if item.match_score >= 88][:3]
    possible = [item for item in companies if item.match_score < 70 and item not in best]
    listed = [item for item in companies if _is_listed(item) and item not in best and item not in possible]
    legal = [item for item in companies if _is_legal_entity(item) and item not in best and item not in possible]
    encyclopedia = [
        item for item in companies if item.provider_id == "wikidata" and item not in best and item not in possible
    ]
    return {
        "best_matches": best,
        "listed_companies": listed,
        "legal_entities": legal,
        "encyclopedia_entities": encyclopedia,
        "news": [],
        "possible_matches": possible,
    }


def canonical_company_key(company: CompanyResult) -> str:
    if company.symbol and company.exchange:
        return f"symbol:{_canonical_symbol(company.symbol)}:{company.exchange.upper()}"
    if company.symbol and company.market:
        return f"symbol-market:{_canonical_symbol(company.symbol)}:{company.market.upper()}"
    if company.lei:
        return f"lei:{company.lei.upper()}"
    if company.wikidata_id:
        return f"wikidata:{company.wikidata_id.upper()}"
    if company.company_number and company.jurisdiction:
        return f"registry:{company.jurisdiction.lower()}:{company.company_number.lower()}"
    name = remove_company_suffix(company.legal_name or company.name or company.display_name)
    if company.country:
        return f"name-country:{name}:{company.country.lower()}"
    return f"name:{name}"


def candidate_match_terms(company: CompanyResult) -> set[str]:
    return {
        company.name,
        company.display_name,
        company.legal_name,
        company.symbol,
        company.lei,
        company.wikidata_id,
        company.company_number,
        company.registry_number,
        *company.aliases,
    } - {""}


def _merge_company(existing: CompanyResult | None, incoming: CompanyResult) -> CompanyResult:
    if existing is None:
        incoming.raw = {
            **incoming.raw,
            "provider_sources": _provider_sources(incoming),
        }
        return incoming
    primary, secondary = (incoming, existing) if _sort_tuple(incoming) > _sort_tuple(existing) else (existing, incoming)
    merged = replace(primary)
    merged.aliases = sorted({*primary.aliases, *secondary.aliases, secondary.name, secondary.display_name} - {""})
    _fill_missing_fields(merged, secondary)
    source_urls = sorted({primary.source_url, secondary.source_url} - {""})
    merged.raw = {
        **secondary.raw,
        **primary.raw,
        "provider_sources": sorted({*_provider_sources(primary), *_provider_sources(secondary)}),
        "source_urls": source_urls,
        "merged_match_scores": {
            primary.provider_id: primary.match_score,
            secondary.provider_id: secondary.match_score,
        },
    }
    merged.from_cache = primary.from_cache or secondary.from_cache
    if secondary.provider_id != primary.provider_id:
        merged.match_score = min(100, max(primary.match_score, secondary.match_score) + 3)
        merged.match_reason = f"{primary.match_reason}；多来源命中"
    return merged


def _provider_sources(company: CompanyResult) -> set[str]:
    raw_sources = company.raw.get("provider_sources")
    if isinstance(raw_sources, Iterable) and not isinstance(raw_sources, (str, bytes)):
        return {str(item) for item in raw_sources if item}
    return {company.provider_id} if company.provider_id else set()


def _sort_tuple(company: CompanyResult) -> tuple[int, int, int, int]:
    exact_symbol = 1 if company.match_reason == "代码完全匹配" else 0
    listed_bonus = 1 if _is_listed(company) else 0
    authority = PROVIDER_AUTHORITY.get(company.provider_id, 50)
    return exact_symbol, company.match_score, listed_bonus, authority


def _is_listed(company: CompanyResult) -> bool:
    return company.category == "financial" or company.provider_id in LISTED_PROVIDERS or bool(company.symbol)


def _is_legal_entity(company: CompanyResult) -> bool:
    return company.category in {"registry", "global"} and company.provider_id in LEGAL_PROVIDERS


def _normalize_symbol(value: str) -> str:
    return re.sub(r"[^A-Z0-9.]", "", (value or "").upper().replace("-", "."))


def _canonical_symbol(value: str) -> str:
    normalized = _normalize_symbol(value)
    if normalized.startswith("HK"):
        digits = re.sub(r"\D", "", normalized[2:])
        return f"HK{digits.zfill(5)}" if digits else normalized
    return normalized


def _acronym_exact(query_terms: set[str], candidate_terms: set[str]) -> bool:
    queries = {term.upper().replace(".", "").replace("-", "") for term in query_terms if term}
    return any(acronym(candidate).upper() in queries for candidate in candidate_terms if candidate)


def title_similarity(left: str, right: str) -> int:
    normalized_left = remove_company_suffix(left)
    normalized_right = remove_company_suffix(right)
    if not normalized_left or not normalized_right:
        return 0
    return int(SequenceMatcher(None, normalized_left, normalized_right).ratio() * 100)


def _fill_missing_fields(primary: CompanyResult, secondary: CompanyResult) -> None:
    for field in [
        "display_name",
        "symbol",
        "exchange",
        "market",
        "country",
        "lei",
        "wikidata_id",
        "wikipedia_url",
        "jurisdiction",
        "company_number",
        "registry_number",
        "legal_name",
        "description",
        "website",
        "source_url",
        "updated_at",
    ]:
        if not getattr(primary, field) and getattr(secondary, field):
            setattr(primary, field, getattr(secondary, field))


def _is_fund_like(company: CompanyResult) -> bool:
    text = " ".join(
        [
            company.name,
            company.display_name,
            company.market,
            str(company.raw.get("ETF", "")),
            str(company.raw.get("is_etf", "")),
        ]
    ).casefold()
    return any(token in text for token in (" etf", "fund", "trust", " etn", "true"))
