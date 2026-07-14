from __future__ import annotations

import re
from dataclasses import dataclass

from cdm_desktop.public_api.query import QueryInfo, analyze_query, remove_company_suffix

_CJK_PATTERN = re.compile(r"[\u3400-\u9fff]")


@dataclass(frozen=True)
class SearchQueryPlan:
    raw_query: str
    normalized_query: str
    query_type: str
    scripts: tuple[str, ...]
    exact_candidates: tuple[str, ...]
    market_candidates: tuple[str, ...]
    fts_terms: tuple[str, ...]
    ngrams: tuple[str, ...]
    provider_plan: tuple[str, ...]
    local_stage_budget_ms: int = 300
    background_stage_budget_ms: int = 5000
    allow_fuzzy: bool = True
    shortlist_limit: int = 100


def build_search_query_plan(value: str | QueryInfo) -> SearchQueryPlan:
    info = value if isinstance(value, QueryInfo) else analyze_query(value)
    normalized = info.normalized_no_suffix or info.normalized
    scripts = ("cjk",) if _CJK_PATTERN.search(normalized) else ("latin",)
    is_symbol = info.kind in {"lei", "hk_symbol", "cn_symbol", "us_symbol", "symbol"}
    exact = _unique((info.symbol, info.upper, normalized, *info.variants[:12]))
    markets = _unique((info.market_hint,))
    fts_terms = _fts_terms(normalized)
    grams = generate_name_ngrams(normalized) if "cjk" in scripts else ()
    compact_length = len(normalized.replace(" ", ""))
    return SearchQueryPlan(
        raw_query=info.original,
        normalized_query=normalized,
        query_type=info.kind,
        scripts=scripts,
        exact_candidates=exact,
        market_candidates=markets,
        fts_terms=fts_terms,
        ngrams=grams,
        provider_plan=("local_exact", "local_prefix", "local_fts", "local_ngram", "public_background"),
        allow_fuzzy=not is_symbol and compact_length >= 3,
        shortlist_limit=100,
    )


def generate_name_ngrams(value: str) -> tuple[str, ...]:
    normalized = remove_company_suffix(value).replace(" ", "")
    if not normalized:
        return ()
    sizes = (2, 3) if _CJK_PATTERN.search(normalized) else (3,)
    grams: list[str] = []
    seen: set[str] = set()
    for size in sizes:
        for index in range(max(0, len(normalized) - size + 1)):
            gram = normalized[index : index + size]
            if gram not in seen:
                seen.add(gram)
                grams.append(gram)
    return tuple(grams[:24])


def _fts_terms(normalized: str) -> tuple[str, ...]:
    terms: list[str] = []
    for token in normalized.split():
        cleaned = token.replace('"', "")
        if len(cleaned) >= 2:
            terms.append(cleaned)
            if len(cleaned) >= 5:
                terms.append(cleaned[: max(3, len(cleaned) - 2)])
    if not terms and len(normalized) >= 2:
        terms.append(normalized)
    return _unique(terms)


def _unique(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value or "").strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return tuple(result)
