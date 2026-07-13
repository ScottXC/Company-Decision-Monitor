from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.cache import ApiCache, cache_key
from cdm_desktop.public_api.http_client import PublicHttpClient
from cdm_desktop.public_api.key_store import ApiKeyStore
from cdm_desktop.public_api.models import CompanyResult, NewsItem, ProviderStatus
from cdm_desktop.public_api.providers import provider_for
from cdm_desktop.public_api.query import query_variants, remove_company_suffix
from cdm_desktop.public_api.ranking import title_similarity
from cdm_desktop.public_api.registry import ProviderRegistry
from cdm_desktop.public_api.settings_store import PublicApiSettingsStore


class CompanyNewsService:
    def __init__(self, paths: AppPaths | None = None) -> None:
        self.registry = ProviderRegistry()
        self.key_store = ApiKeyStore(paths)
        self.cache = ApiCache(paths)
        self.http = PublicHttpClient()
        self.settings = PublicApiSettingsStore(paths)

    def get_news(self, company: CompanyResult, limit: int = 20) -> tuple[list[NewsItem], list[ProviderStatus]]:
        key = cache_key(
            "company_news",
            "aggregate",
            {"symbol": company.symbol, "provider": company.provider_id, "limit": limit},
            company.name,
        )
        cached = self.cache.get(key)
        if isinstance(cached, list):
            news = [NewsItem.from_dict(item) for item in cached if isinstance(item, dict)]
            for item in news:
                item.from_cache = True
            return news, [
                ProviderStatus("cache", "Local cache", "fallback", "enabled", "Related news loaded from local cache.")
            ]

        statuses: list[ProviderStatus] = []
        news: list[NewsItem] = []
        provider_order = ["rss"]
        if self.settings.advanced_api_providers_enabled():
            provider_order.extend(["marketaux", "fmp"])
        for provider_id in provider_order:
            meta = next((item for item in self.registry.all() if item.provider_id == provider_id), None)
            if meta is None:
                continue
            if meta.requires_key and not self.key_store.get(meta.key_name or ""):
                statuses.append(
                    ProviderStatus(
                        meta.provider_id,
                        meta.display_name,
                        meta.category,
                        "not_configured",
                        f"{meta.key_name} is not configured; news provider skipped.",
                    )
                )
                continue
            provider = provider_for(meta, self.key_store, self.http, self.cache)
            provider_rows: list[NewsItem] = []
            provider_error = None
            for term in build_news_query_terms(company):
                symbol = company.symbol if term == company.symbol else ""
                rows, error = provider.news(symbol=symbol, company_name=term, limit=limit)
                if error and error.state != "empty":
                    provider_error = error
                provider_rows.extend(rows)
                if rows:
                    break
            rows = provider_rows
            error = provider_error
            if error:
                statuses.append(
                    ProviderStatus(
                        meta.provider_id,
                        meta.display_name,
                        meta.category,
                        error.state,
                        error.message,
                        str(error.status_code or ""),
                    )
                )
                continue
            statuses.append(
                ProviderStatus(meta.provider_id, meta.display_name, meta.category, "enabled", "Related news returned.")
            )
            news.extend(_filter_relevant_news(_score_news(rows, company)))

        news = _dedupe_news(news)[:limit]
        if news:
            self.cache.set(key, [item.to_dict() for item in news], ttl_seconds=3600)
            return news, statuses

        stale = self.cache.get_stale(key)
        if isinstance(stale, list):
            news = [NewsItem.from_dict(item) for item in stale if isinstance(item, dict)]
            for item in news:
                item.from_cache = True
            statuses.append(
                ProviderStatus(
                    "cache",
                    "Local cache",
                    "fallback",
                    "enabled",
                    "News sources failed; showing cached news.",
                )
            )
            return news, statuses
        return [], statuses


def _dedupe_news(news: list[NewsItem]) -> list[NewsItem]:
    deduped: dict[str, NewsItem] = {}
    for item in news:
        keys = [_canonical_news_key(item), f"title:{_normalize_title(item.title)}"]
        existing = next((deduped[key] for key in keys if key in deduped), None)
        if existing is None:
            similar_key = next(
                (key for key, other in deduped.items() if title_similarity(item.title, other.title) >= 92),
                None,
            )
            existing = deduped.get(similar_key or "")
        if existing is None or _news_sort_tuple(item) > _news_sort_tuple(existing):
            for key in keys:
                deduped[key] = item
    unique = {id(item): item for item in deduped.values()}.values()
    return sorted(unique, key=_news_sort_tuple, reverse=True)


def build_news_query_terms(company: CompanyResult) -> list[str]:
    terms = [company.symbol, company.display_name, company.name, company.legal_name, *company.aliases]
    expanded: list[str] = []
    seen: set[str] = set()
    for term in terms:
        _append_news_term(expanded, seen, term)
    for term in terms:
        for variant in query_variants(term, max_terms=4) if term else []:
            _append_news_term(expanded, seen, variant)
    return expanded[:16] or [company.name or company.symbol]


def _news_query_terms(company: CompanyResult) -> list[str]:
    return build_news_query_terms(company)


def _append_news_term(expanded: list[str], seen: set[str], value: str) -> None:
    cleaned = (value or "").strip()
    key = cleaned.casefold()
    if cleaned and key not in seen:
        seen.add(key)
        expanded.append(cleaned)


def _score_news(news: list[NewsItem], company: CompanyResult) -> list[NewsItem]:
    terms = [remove_company_suffix(term) for term in _news_query_terms(company)]
    symbols = {company.symbol.upper(), *[alias.upper() for alias in company.aliases if alias.isupper()]}
    for item in news:
        if item.provider_id == "xueqiu_external":
            item.relevance_score = 0
            continue
        haystack_title = remove_company_suffix(item.title)
        haystack_snippet = remove_company_suffix(item.snippet)
        score = 20
        if any(term and term == haystack_title for term in terms):
            score += 60
        elif any(term and term in haystack_title for term in terms):
            score += 45
        if any(symbol and re.search(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", item.title.upper()) for symbol in symbols):
            score += 35
        if any(term and term in haystack_snippet for term in terms):
            score += 25
        if _financial_source(item.source):
            score += 5
        if _weak_generic_only(item.title, terms):
            score -= 20
        item.relevance_score = max(0, min(score, 100))
    return news


def _filter_relevant_news(news: list[NewsItem]) -> list[NewsItem]:
    return [item for item in news if item.provider_id != "xueqiu_external" and item.relevance_score >= 40]


def _news_sort_tuple(item: NewsItem) -> tuple[int, str, int]:
    provider_priority = {"marketaux": 3, "fmp": 2}.get(item.provider_id, 1)
    return item.relevance_score, item.published_at, provider_priority


def _normalize_title(value: str) -> str:
    cleaned = remove_company_suffix(value)
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", cleaned.casefold())


def _canonical_news_key(item: NewsItem) -> str:
    if item.url:
        return f"url:{_canonical_url(item.url)}"
    return item.dedupe_key()


def _canonical_url(value: str) -> str:
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return value.strip().lower()
    ignored_prefixes = ("utm_",)
    ignored_keys = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src"}
    query = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if key not in ignored_keys and not any(key.startswith(prefix) for prefix in ignored_prefixes)
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            urlencode(query, doseq=True),
            "",
        )
    )


def _financial_source(source: str) -> bool:
    lowered = (source or "").casefold()
    return any(token in lowered for token in ("market", "finance", "reuters", "bloomberg", "cnbc", "wsj", "financial"))


def _weak_generic_only(title: str, terms: list[str]) -> bool:
    lowered = remove_company_suffix(title)
    generic = {"group", "holding", "company", "market", "stock", "shares"}
    return bool(lowered) and not any(term and term in lowered for term in terms) and any(word in lowered for word in generic)
