from __future__ import annotations

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.cache import ApiCache, cache_key
from cdm_desktop.public_api.http_client import PublicHttpClient
from cdm_desktop.public_api.key_store import ApiKeyStore
from cdm_desktop.public_api.models import CompanyResult, NewsItem, ProviderStatus
from cdm_desktop.public_api.providers import provider_for
from cdm_desktop.public_api.registry import ProviderRegistry


class CompanyNewsService:
    def __init__(self, paths: AppPaths | None = None) -> None:
        self.registry = ProviderRegistry()
        self.key_store = ApiKeyStore(paths)
        self.cache = ApiCache(paths)
        self.http = PublicHttpClient()

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
        for provider_id in ["marketaux", "fmp"]:
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
            rows, error = provider.news(symbol=company.symbol, company_name=company.name, limit=limit)
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
            news.extend(rows)

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
        key = item.dedupe_key()
        if key not in deduped:
            deduped[key] = item
    return sorted(deduped.values(), key=lambda item: item.published_at, reverse=True)
