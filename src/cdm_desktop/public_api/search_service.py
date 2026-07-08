from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.cache import ApiCache, cache_key
from cdm_desktop.public_api.http_client import PublicHttpClient
from cdm_desktop.public_api.key_store import ApiKeyStore
from cdm_desktop.public_api.models import (
    CompanyResult,
    NewsItem,
    ProviderMeta,
    ProviderStatus,
    SearchResponse,
)
from cdm_desktop.public_api.providers import provider_for
from cdm_desktop.public_api.registry import ProviderRegistry

SearchRegion = str
SearchScope = str

REGION_OPTIONS: tuple[tuple[SearchRegion, str, str], ...] = (
    ("all", "全部地区", "调用精简后的核心数据源，覆盖较广但仍会跳过无关 stub。"),
    ("us", "美国 / 美股", "优先调用美国证券目录，再调用已配置的美股增强源、GLEIF 和新闻源。"),
    ("cn", "中国大陆", "优先调用已配置的财务数据源、GLEIF 和新闻源。"),
    ("hk", "香港 / 港股", "优先调用已配置的财务数据源、GLEIF 和新闻源。"),
    ("uk", "英国", "优先调用 UK Companies House，再调用 OpenCorporates、GLEIF 和新闻源。"),
    ("eu", "欧洲", "优先调用 GLEIF、OpenCorporates 和新闻源。"),
    ("no", "挪威", "优先调用 Norway BRREG，再调用 GLEIF、OpenCorporates 和新闻源。"),
    ("global", "全球法人", "优先调用 GLEIF、OpenCorporates 和新闻源。"),
    ("news", "新闻优先", "优先调用新闻 provider，用于先看媒体提及。"),
)

REGION_PROVIDER_PRIORITY: dict[SearchRegion, tuple[str, ...]] = {
    "all": (
        "nasdaq_directory",
        "gleif",
        "fmp",
        "alpha_vantage",
        "companies_house",
        "norway_brreg",
        "opencorporates",
        "marketaux",
        "rss",
    ),
    "us": ("nasdaq_directory", "fmp", "alpha_vantage", "gleif", "marketaux", "rss"),
    "cn": ("fmp", "alpha_vantage", "gleif", "marketaux", "rss"),
    "hk": ("fmp", "alpha_vantage", "gleif", "marketaux", "rss"),
    "uk": ("companies_house", "opencorporates", "gleif", "fmp", "marketaux", "rss"),
    "eu": ("gleif", "opencorporates", "fmp", "marketaux", "rss"),
    "no": ("norway_brreg", "gleif", "opencorporates", "marketaux", "rss"),
    "global": ("gleif", "opencorporates", "marketaux", "rss"),
    "news": ("marketaux", "rss"),
}

SCOPE_PROVIDER_CATEGORIES: dict[SearchScope, set[str]] = {
    "all": set(),
    "financial": {"financial"},
    "entity": {"registry", "global"},
    "news": {"news"},
    "related": set(),
}


class PublicSearchService:
    def __init__(self, paths: AppPaths | None = None) -> None:
        self.registry = ProviderRegistry()
        self.key_store = ApiKeyStore(paths)
        self.cache = ApiCache(paths)
        self.http = PublicHttpClient()

    def search(
        self,
        query: str,
        limit: int = 10,
        use_cache: bool = True,
        *,
        region_filter: SearchRegion = "all",
        scope_filter: SearchScope = "all",
    ) -> SearchResponse:
        normalized = query.strip()
        if not normalized:
            return SearchResponse(query=query, companies=[], news=[], statuses=[])
        selected_providers = self._selected_providers(region_filter, scope_filter)
        key = cache_key(
            "public_search",
            "search",
            {
                "limit": limit,
                "region_filter": region_filter,
                "scope_filter": scope_filter,
                "providers": [provider.provider_id for provider in selected_providers],
            },
            normalized,
        )
        if use_cache:
            cached = self.cache.get(key)
            if isinstance(cached, dict):
                return _response_from_cache(cached)

        companies: list[CompanyResult] = []
        news: list[NewsItem] = []
        statuses: list[ProviderStatus] = [
            ProviderStatus(
                "provider_filter",
                "地区初筛",
                "fallback",
                "enabled",
                (
                    f"已按“{region_label(region_filter)} / {scope_label(scope_filter)}”"
                    f"选择 {len(selected_providers)} 个数据源进行搜索。"
                ),
            )
        ]
        for meta in selected_providers:
            provider = provider_for(meta, self.key_store, self.http)
            provider_companies, provider_news, error = provider.search(normalized, limit=limit)
            companies.extend(provider_companies)
            news.extend(provider_news)
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
            else:
                state = "enabled" if provider_companies or provider_news else "empty"
                message = "已返回真实 provider 数据。" if state == "enabled" else "provider 返回空数据。"
                statuses.append(
                    ProviderStatus(meta.provider_id, meta.display_name, meta.category, state, message)
                )
        response = SearchResponse(
            query=normalized,
            companies=_dedupe_companies(companies)[:limit],
            news=news[:limit],
            statuses=statuses,
        )
        self.cache.set(key, _response_to_cache(response), ttl_seconds=300)
        return response

    def selected_provider_ids(
        self,
        *,
        region_filter: SearchRegion = "all",
        scope_filter: SearchScope = "all",
    ) -> list[str]:
        return [provider.provider_id for provider in self._selected_providers(region_filter, scope_filter)]

    def selected_provider_count(
        self,
        *,
        region_filter: SearchRegion = "all",
        scope_filter: SearchScope = "all",
    ) -> int:
        return len(self._selected_providers(region_filter, scope_filter))

    def provider_statuses(self) -> list[ProviderStatus]:
        statuses = []
        for meta in self.registry.all():
            configured, masked = self.key_store.status(meta.key_name)
            if not meta.implemented:
                state = "disabled"
                message = meta.notes or "当前版本为 registry/stub，暂未接入真实请求。"
            elif meta.requires_key and not configured:
                state = "not_configured"
                message = f"未配置 {meta.key_name}，provider 将自动跳过。"
            else:
                state = "enabled"
                message = f"可用。Key 状态：{masked}。"
            statuses.append(
                ProviderStatus(meta.provider_id, meta.display_name, meta.category, state, message)
            )
        return statuses

    def test_provider_connectivity(
        self,
        *,
        probe_query: str = "Apple",
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> list[ProviderStatus]:
        providers = self.registry.all()
        total = len(providers)
        statuses: list[ProviderStatus] = []
        for index, meta in enumerate(providers, start=1):
            if progress_callback:
                progress_callback(index - 1, total, f"正在测试 {meta.display_name}")
            if not meta.implemented:
                status = ProviderStatus(
                    meta.provider_id,
                    meta.display_name,
                    meta.category,
                    "disabled",
                    meta.notes or "当前版本暂未接入真实请求。",
                )
            elif meta.requires_key and not self.key_store.get(meta.key_name or ""):
                status = ProviderStatus(
                    meta.provider_id,
                    meta.display_name,
                    meta.category,
                    "not_configured",
                    f"未配置 {meta.key_name}，已跳过该增强数据源。",
                )
            else:
                provider = provider_for(meta, self.key_store, self.http)
                companies, news, error = provider.search(probe_query, limit=1)
                if error:
                    status = ProviderStatus(
                        meta.provider_id,
                        meta.display_name,
                        meta.category,
                        error.state,
                        error.message,
                        str(error.status_code or ""),
                    )
                else:
                    state = "enabled" if companies or news else "empty"
                    message = "连接成功，provider 返回了数据。" if state == "enabled" else "连接成功，但本次探测没有返回结果。"
                    status = ProviderStatus(meta.provider_id, meta.display_name, meta.category, state, message)
            statuses.append(status)
            if progress_callback:
                progress_callback(index, total, f"已完成 {meta.display_name}")
        return statuses

    def _selected_providers(self, region_filter: SearchRegion, scope_filter: SearchScope) -> list[ProviderMeta]:
        implemented = self.registry.implemented()
        implemented_by_id = {provider.provider_id: provider for provider in implemented}
        region_priority = REGION_PROVIDER_PRIORITY.get(region_filter, REGION_PROVIDER_PRIORITY["all"])
        category_ids = SCOPE_PROVIDER_CATEGORIES.get(scope_filter, set())
        selected: list[ProviderMeta] = []
        for provider_id in region_priority:
            provider = implemented_by_id.get(provider_id)
            if provider is None:
                continue
            if category_ids and provider.category not in category_ids:
                continue
            selected.append(provider)
        if selected:
            return selected
        if category_ids:
            category_matches = [provider for provider in implemented if provider.category in category_ids]
            if category_matches:
                return category_matches
        return [provider for provider_id in REGION_PROVIDER_PRIORITY["all"] if (provider := implemented_by_id.get(provider_id))]


def region_label(region_filter: SearchRegion) -> str:
    for value, label, _description in REGION_OPTIONS:
        if value == region_filter:
            return label
    return "全部地区"


def scope_label(scope_filter: SearchScope) -> str:
    labels = {
        "all": "全部类型",
        "financial": "上市公司",
        "entity": "法人实体",
        "news": "新闻",
        "related": "可能相关",
    }
    return labels.get(scope_filter, "全部类型")


def _dedupe_companies(companies: list[CompanyResult]) -> list[CompanyResult]:
    deduped: dict[str, CompanyResult] = {}
    for company in companies:
        key = company.dedupe_key()
        existing = deduped.get(key)
        if existing is None or company.match_score > existing.match_score:
            deduped[key] = company
    return sorted(deduped.values(), key=lambda item: item.match_score, reverse=True)


def _response_to_cache(response: SearchResponse) -> dict[str, object]:
    return {
        "query": response.query,
        "companies": [company.to_dict() for company in response.companies],
        "news": [item.__dict__ for item in response.news],
        "statuses": [
            {
                "provider_id": item.provider_id,
                "display_name": item.display_name,
                "category": item.category,
                "state": item.state,
                "message": item.message,
                "last_error": item.last_error,
                "checked_at": item.checked_at.isoformat(),
            }
            for item in response.statuses
        ],
    }


def _response_from_cache(data: dict[str, object]) -> SearchResponse:
    companies = [
        CompanyResult.from_dict(item)
        for item in data.get("companies", [])
        if isinstance(item, dict)
    ]
    news = [NewsItem(**item) for item in data.get("news", []) if isinstance(item, dict)]
    statuses = []
    for item in data.get("statuses", []):
        if not isinstance(item, dict):
            continue
        value = dict(item)
        checked = value.get("checked_at")
        if isinstance(checked, str):
            try:
                value["checked_at"] = datetime.fromisoformat(checked)
            except ValueError:
                value["checked_at"] = datetime.utcnow()
        statuses.append(ProviderStatus(**value))
    return SearchResponse(
        query=str(data.get("query") or ""),
        companies=companies,
        news=news,
        statuses=statuses,
        from_cache=True,
    )
