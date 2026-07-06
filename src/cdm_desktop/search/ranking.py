from __future__ import annotations

from dataclasses import replace

from rapidfuzz import fuzz

from cdm_desktop.search.models import CompanySearchCandidate, SearchScope

PROVIDER_AUTHORITY = {
    "sec": 95,
    "nasdaq_trader": 90,
    "hkex": 90,
    "stock_connect": 80,
    "hkexnews": 75,
    "rss_news": 55,
    "company_ir": 70,
}


def score_candidate(
    candidate: CompanySearchCandidate,
    query: str,
    scope: SearchScope,
    *,
    provider_id: str,
    freshness_score: float = 80,
) -> CompanySearchCandidate:
    normalized_query = query.strip().lower()
    ticker = candidate.ticker.strip().lower()
    name = candidate.name.strip().lower()
    legal_name = candidate.legal_name.strip().lower()
    exact_ticker = 100.0 if normalized_query and normalized_query == ticker else 0.0
    exact_name = 100.0 if normalized_query and normalized_query in {name, legal_name} else 0.0
    contains = 100.0 if normalized_query and (normalized_query in name or normalized_query in legal_name) else 0.0
    fuzzy_name = float(fuzz.WRatio(normalized_query, name)) if normalized_query and name else 0.0
    name_contains = max(contains, fuzzy_name)
    provider_authority = PROVIDER_AUTHORITY.get(provider_id, 50)
    market_scope = 100.0 if _scope_matches_market(scope, candidate.market) else 40.0
    score = (
        0.35 * exact_ticker
        + 0.25 * exact_name
        + 0.15 * name_contains
        + 0.10 * provider_authority
        + 0.10 * freshness_score
        + 0.05 * market_scope
    )
    if exact_ticker or exact_name:
        score = max(score, 92.0)
    elif contains:
        score = max(score, 78.0)
    reason = candidate.match_reason or _reason(exact_ticker, exact_name, contains, fuzzy_name)
    return replace(candidate, confidence_score=round(min(score, 100.0), 2), match_reason=reason)


def dedupe_and_rank(candidates: list[CompanySearchCandidate]) -> list[CompanySearchCandidate]:
    best: dict[str, CompanySearchCandidate] = {}
    for candidate in candidates:
        key = _candidate_key(candidate)
        existing = best.get(key)
        if existing is None:
            best[key] = candidate
            continue
        winner = candidate if _authority(candidate) > _authority(existing) else existing
        loser = existing if winner is candidate else candidate
        providers = tuple(
            dict.fromkeys(
                [
                    *(winner.contributing_providers or (winner.source_provider,)),
                    *(loser.contributing_providers or (loser.source_provider,)),
                ]
            )
        )
        best[key] = replace(
            winner,
            confidence_score=max(winner.confidence_score, loser.confidence_score),
            contributing_providers=providers,
        )
    return sorted(best.values(), key=lambda item: item.confidence_score, reverse=True)


def _candidate_key(candidate: CompanySearchCandidate) -> str:
    ticker = candidate.ticker.upper().strip()
    exchange = candidate.exchange.upper().strip()
    if ticker and exchange:
        return f"{ticker}:{exchange}"
    return f"{candidate.name.lower().strip()}:{candidate.market}"


def _authority(candidate: CompanySearchCandidate) -> float:
    provider_id = _provider_id(candidate.source_provider)
    return PROVIDER_AUTHORITY.get(provider_id, 50) + candidate.confidence_score / 100


def _provider_id(source_provider: str) -> str:
    value = source_provider.lower()
    if "sec" in value:
        return "sec"
    if "nasdaq" in value:
        return "nasdaq_trader"
    if "stock connect" in value:
        return "stock_connect"
    if "hkex" in value:
        return "hkex"
    if "rss" in value:
        return "rss_news"
    return value


def _scope_matches_market(scope: SearchScope, market: str) -> bool:
    if scope == "all":
        return True
    return {
        "us": "美股",
        "hk": "港股",
        "a_share": "A股",
        "filings": "公告/披露",
        "news": "新闻/网页",
    }.get(scope, "") in {market, ""}


def _reason(exact_ticker: float, exact_name: float, contains: float, fuzzy: float) -> str:
    if exact_ticker:
        return "代码完全匹配"
    if exact_name:
        return "名称完全匹配"
    if contains:
        return "名称包含关键词"
    if fuzzy >= 70:
        return "名称相似匹配"
    return "公开来源匹配"
