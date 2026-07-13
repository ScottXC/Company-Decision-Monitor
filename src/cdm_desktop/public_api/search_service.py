from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import UTC, datetime

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.cache import ApiCache, cache_key
from cdm_desktop.public_api.crawlergo_provider import CrawlergoWebEvidenceProvider
from cdm_desktop.public_api.http_client import PublicHttpClient
from cdm_desktop.public_api.key_store import ApiKeyStore
from cdm_desktop.public_api.models import (
    CompanyResult,
    NewsItem,
    ProviderError,
    ProviderMeta,
    ProviderStatus,
    SearchResponse,
    SearchTiming,
)
from cdm_desktop.public_api.provider_health import ProviderHealthTracker
from cdm_desktop.public_api.providers import provider_for
from cdm_desktop.public_api.query import QueryInfo, analyze_query
from cdm_desktop.public_api.ranking import group_companies, rank_and_dedupe_companies
from cdm_desktop.public_api.registry import ProviderRegistry
from cdm_desktop.public_api.settings_store import PublicApiSettingsStore

SearchRegion = str
SearchScope = str

LOCAL_PROVIDER_IDS = {"symbol_universe", "nasdaq_directory"}
SEARCH_EXCLUDED_PROVIDER_IDS = {"rss", "marketaux", "xueqiu_external"}
PUBLIC_ENRICHMENT_TIMEOUT_SECONDS = 3.0
PUBLIC_ENRICHMENT_BUDGET_SECONDS = 5.0
MAX_BACKGROUND_PROVIDER_TASKS = 4
MAX_BACKGROUND_PROVIDER_WORKERS = 3
SLOW_SEARCH_MS = 1000.0
LOCAL_CACHE_MAX_ITEMS = 160
LOCAL_CACHE_TTL_SECONDS = 1800.0

logger = logging.getLogger(__name__)

REGION_OPTIONS: tuple[tuple[SearchRegion, str, str], ...] = (
    ("all", "全部地区", "先查询内置开源证券索引，再后台补充公开公司来源；新闻在详情页加载。"),
    ("us", "美国 / 美股", "优先使用内置开源证券索引、美国证券目录、公开百科信息和 GLEIF。"),
    ("cn", "中国大陆", "先查询内置索引，再后台补充 AKShare experimental、Wikidata 和 GLEIF。"),
    ("hk", "香港 / 港股", "先查询内置索引，再后台补充 AKShare experimental、Wikidata 和 GLEIF。"),
    ("uk", "英国", "先查询内置索引，再后台补充 Wikidata 和 GLEIF；高级 API 默认关闭。"),
    ("eu", "欧洲", "先查询内置索引，再后台补充 Wikidata 和 GLEIF。"),
    ("no", "挪威", "先查询内置索引，再后台补充 BRREG、Wikidata 和 GLEIF。"),
    ("global", "全球法人", "先查询内置索引，再后台补充 Wikidata 和 GLEIF。"),
    ("news", "新闻（详情页）", "普通搜索不加载新闻；请先选择公司，再在详情页加载相关新闻。"),
)

REGION_PROVIDER_PRIORITY: dict[SearchRegion, tuple[str, ...]] = {
    "all": (
        "symbol_universe",
        "nasdaq_directory",
        "akshare",
        "wikidata",
        "gleif",
        "norway_brreg",
        "rss",
        "xueqiu_external",
    ),
    "us": ("symbol_universe", "nasdaq_directory", "wikidata", "gleif", "rss", "xueqiu_external"),
    "cn": ("symbol_universe", "akshare", "wikidata", "gleif", "rss", "xueqiu_external"),
    "hk": ("symbol_universe", "akshare", "wikidata", "gleif", "rss", "xueqiu_external"),
    "uk": ("symbol_universe", "wikidata", "gleif", "rss", "xueqiu_external"),
    "eu": ("symbol_universe", "wikidata", "gleif", "rss", "xueqiu_external"),
    "no": ("symbol_universe", "norway_brreg", "wikidata", "gleif", "rss", "xueqiu_external"),
    "global": ("symbol_universe", "wikidata", "gleif", "rss", "xueqiu_external"),
    "news": ("rss",),
}

ADVANCED_PROVIDER_PRIORITY: tuple[str, ...] = (
    "fmp",
    "alpha_vantage",
    "marketaux",
    "companies_house",
    "opencorporates",
)

SCOPE_PROVIDER_CATEGORIES: dict[SearchScope, set[str]] = {
    "all": set(),
    "financial": {"financial", "symbol_universe", "experimental"},
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
        self.enrichment_http = PublicHttpClient(
            timeout_seconds=PUBLIC_ENRICHMENT_TIMEOUT_SECONDS,
            retry_count=0,
        )
        self.health = ProviderHealthTracker()
        self.settings = PublicApiSettingsStore(paths)
        self._provider_instances: dict[tuple[str, bool], object] = {}
        self._local_cache: OrderedDict[str, tuple[float, SearchResponse]] = OrderedDict()
        self._cache_lock = threading.Lock()

    def search(
        self,
        query: str,
        limit: int = 10,
        use_cache: bool = True,
        *,
        region_filter: SearchRegion = "all",
        scope_filter: SearchScope = "all",
        cancel_check: Callable[[], bool] | None = None,
    ) -> SearchResponse:
        local = self.search_local(
            query,
            limit=limit,
            use_cache=use_cache,
            region_filter=region_filter,
            scope_filter=scope_filter,
            cancel_check=cancel_check,
        )
        return self.enrich_search(
            query,
            local,
            limit=limit,
            use_cache=use_cache,
            region_filter=region_filter,
            scope_filter=scope_filter,
            cancel_check=cancel_check,
        )

    def search_local(
        self,
        query: str,
        limit: int = 20,
        use_cache: bool = True,
        *,
        region_filter: SearchRegion = "all",
        scope_filter: SearchScope = "all",
        cancel_check: Callable[[], bool] | None = None,
    ) -> SearchResponse:
        started = time.perf_counter()
        normalize_started = time.perf_counter()
        query_info = analyze_query(query)
        timing = SearchTiming(
            query=query_info.original.strip(),
            normalize_ms=(time.perf_counter() - normalize_started) * 1000,
        )
        if query_info.kind == "empty":
            return SearchResponse(query=query, companies=[], news=[], statuses=[], timing=timing)
        if _is_cancelled(cancel_check):
            timing.cancelled = True
            return SearchResponse(query=query, companies=[], news=[], statuses=[], timing=timing)

        memory_key = self._local_cache_key(query_info, limit, region_filter, scope_filter)
        if use_cache and (cached := self._get_local_cache(memory_key)) is not None:
            cached.timing = SearchTiming(
                query=query_info.original.strip(),
                total_ms=(time.perf_counter() - started) * 1000,
                cache_hit=True,
                result_count=len(cached.companies),
            )
            cached.from_cache = True
            return cached

        local_metas = [
            meta
            for meta in self._selected_providers(region_filter, scope_filter)
            if meta.provider_id in LOCAL_PROVIDER_IDS
        ]
        companies: list[CompanyResult] = []
        statuses = [
            ProviderStatus(
                "local_search",
                "本地开源索引",
                "fallback",
                "enabled",
                "首批结果仅使用内置索引和已下载目录缓存，不访问新闻或公司详情。",
            )
        ]
        local_started = time.perf_counter()
        for meta in local_metas:
            if _is_cancelled(cancel_check):
                return _cancelled_local_response(query_info, statuses, timing, started)
            provider_started = time.perf_counter()
            provider = self._provider(meta, enrichment=False)
            if meta.provider_id == "nasdaq_directory" and hasattr(provider, "search_cached"):
                rows, _news, error = provider.search_cached(query_info.original, limit=limit)  # type: ignore[attr-defined]
            else:
                rows, _news, error = provider.search(query_info.original, limit=limit)  # type: ignore[attr-defined]
            provider_ms = (time.perf_counter() - provider_started) * 1000
            timing.provider_timings[meta.provider_id] = provider_ms
            if meta.provider_id == "symbol_universe":
                timing.local_index_ms = provider_ms
                provider_timing = getattr(provider, "last_timing", {})
                timing.fuzzy_ms = float(provider_timing.get("fuzzy_ms", 0.0))
                timing.candidate_shortlist_size = int(provider_timing.get("shortlist_size", 0))
                timing.fuzzy_candidate_count = int(provider_timing.get("shortlist_size", 0))
            companies.extend(rows)
            if _is_cancelled(cancel_check):
                return _cancelled_local_response(query_info, statuses, timing, started)
            if error and error.state not in {"empty", "cache_miss"}:
                statuses.append(
                    ProviderStatus(meta.provider_id, meta.display_name, meta.category, error.state, error.message)
                )
            else:
                state = "enabled" if rows else "empty"
                message = "已返回本地候选。" if rows else (error.message if error else "本地缓存无匹配结果。")
                statuses.append(ProviderStatus(meta.provider_id, meta.display_name, meta.category, state, message))
        timing.provider_ms = (time.perf_counter() - local_started) * 1000
        if _is_cancelled(cancel_check):
            return _cancelled_local_response(query_info, statuses, timing, started)
        rank_started = time.perf_counter()
        ranked = rank_and_dedupe_companies(companies, query_info)[:limit]
        timing.ranking_ms = (time.perf_counter() - rank_started) * 1000
        timing.total_ms = (time.perf_counter() - started) * 1000
        timing.result_count = len(ranked)
        response = SearchResponse(
            query=query_info.original.strip(),
            companies=ranked,
            news=[],
            statuses=statuses,
            grouped_results=group_companies(ranked),
            timing=timing,
        )
        self._put_local_cache(memory_key, response)
        self._log_timing(timing, stage="local")
        return response

    def enrich_search(
        self,
        query: str,
        base_response: SearchResponse,
        limit: int = 20,
        use_cache: bool = True,
        *,
        region_filter: SearchRegion = "all",
        scope_filter: SearchScope = "all",
        cancel_check: Callable[[], bool] | None = None,
    ) -> SearchResponse:
        started = time.perf_counter()
        query_info = analyze_query(query)
        timing = SearchTiming(query=query_info.original.strip())
        if _is_cancelled(cancel_check):
            timing.cancelled = True
            return _cancelled_enrichment_response(base_response, timing)
        metas = [
            meta
            for meta in self._selected_providers(region_filter, scope_filter)
            if meta.provider_id not in LOCAL_PROVIDER_IDS | SEARCH_EXCLUDED_PROVIDER_IDS
        ][:MAX_BACKGROUND_PROVIDER_TASKS]
        key = cache_key(
            "public_search",
            "background_enrichment",
            {
                "limit": limit,
                "region_filter": region_filter,
                "scope_filter": scope_filter,
                "providers": [meta.provider_id for meta in metas],
            },
            query_info.normalized,
        )
        if use_cache:
            cached = self.cache.get(key)
            if isinstance(cached, dict):
                if _is_cancelled(cancel_check):
                    timing.cancelled = True
                    return _cancelled_enrichment_response(base_response, timing)
                response = _response_from_cache(cached)
                response.timing = SearchTiming(
                    query=query_info.original.strip(),
                    total_ms=(time.perf_counter() - started) * 1000,
                    cache_hit=True,
                    result_count=len(response.companies),
                )
                return _merge_search_responses(base_response, response, query_info, limit)

        statuses: list[ProviderStatus] = []
        errors: list[ProviderError] = []
        warnings: list[str] = []
        companies: list[CompanyResult] = []
        runnable: list[ProviderMeta] = []
        for meta in metas:
            if _is_cancelled(cancel_check):
                timing.cancelled = True
                return _cancelled_enrichment_response(base_response, timing)
            configured = not meta.requires_key or bool(self.key_store.get(meta.key_name or ""))
            if meta.requires_key and not configured:
                error = ProviderError(meta.provider_id, "not_configured", f"未配置 {meta.key_name}，已跳过后台增强。")
                errors.append(error)
                statuses.append(ProviderStatus(meta.provider_id, meta.display_name, meta.category, error.state, error.message))
                continue
            skipped = self.health.should_skip(meta.provider_id, meta.display_name)
            if skipped:
                statuses.append(skipped)
                continue
            runnable.append(meta)

        executor = ThreadPoolExecutor(
            max_workers=min(MAX_BACKGROUND_PROVIDER_WORKERS, max(1, len(runnable))),
            thread_name_prefix="search-enrich",
        )
        futures: dict[Future[tuple[list[CompanyResult], ProviderError | None, float]], ProviderMeta] = {
            executor.submit(self._search_enrichment_provider, meta, query_info, limit, cancel_check): meta
            for meta in runnable
        }
        done, pending = wait(futures, timeout=PUBLIC_ENRICHMENT_BUDGET_SECONDS)
        if _is_cancelled(cancel_check):
            for future in futures:
                future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            timing.cancelled = True
            timing.total_ms = (time.perf_counter() - started) * 1000
            return _cancelled_enrichment_response(base_response, timing)
        for future in done:
            if _is_cancelled(cancel_check):
                break
            meta = futures[future]
            try:
                rows, error, elapsed_ms = future.result()
            except Exception:  # noqa: BLE001
                rows = []
                error = ProviderError(meta.provider_id, "provider_unavailable", "该公开数据源暂时不可用，已保留本地结果。")
                elapsed_ms = 0.0
            timing.provider_timings[meta.provider_id] = elapsed_ms
            companies.extend(rows)
            if error and error.state != "empty":
                errors.append(error)
                statuses.append(ProviderStatus(meta.provider_id, meta.display_name, meta.category, error.state, error.message))
                self.health.record_error(meta.provider_id, meta.display_name, error, configured=True)
            else:
                self.health.record_success(meta.provider_id, meta.display_name)
                statuses.append(
                    ProviderStatus(
                        meta.provider_id,
                        meta.display_name,
                        meta.category,
                        "enabled" if rows else "empty",
                        "后台公开数据补充完成。" if rows else "公开数据源返回空结果。",
                    )
                )
        for future in pending:
            meta = futures[future]
            future.cancel()
            warning = "部分公开数据源响应较慢，已停止等待并保留当前结果。"
            timeout_error = ProviderError(
                meta.provider_id,
                "network_timeout",
                warning,
                retryable=True,
            )
            self.health.record_error(meta.provider_id, meta.display_name, timeout_error, configured=True)
            warnings.append(warning)
            statuses.append(ProviderStatus(meta.provider_id, meta.display_name, meta.category, "network_timeout", warning))
        executor.shutdown(wait=False, cancel_futures=True)

        timing.provider_ms = (time.perf_counter() - started) * 1000
        if _is_cancelled(cancel_check):
            timing.cancelled = True
            timing.total_ms = (time.perf_counter() - started) * 1000
            return _cancelled_enrichment_response(base_response, timing)
        rank_started = time.perf_counter()
        ranked = rank_and_dedupe_companies(companies, query_info)[:limit]
        timing.ranking_ms = (time.perf_counter() - rank_started) * 1000
        timing.total_ms = (time.perf_counter() - started) * 1000
        timing.result_count = len(ranked)
        enrichment = SearchResponse(
            query=query_info.original.strip(),
            companies=ranked,
            news=[],
            statuses=statuses,
            grouped_results=group_companies(ranked),
            warnings=warnings,
            errors=errors,
            timing=timing,
        )
        self.cache.set(key, _response_to_cache(enrichment), ttl_seconds=21600)
        merged = _merge_search_responses(base_response, enrichment, query_info, limit)
        self._log_timing(timing, stage="enrichment")
        return merged

    def _search_enrichment_provider(
        self,
        meta: ProviderMeta,
        query_info: QueryInfo,
        limit: int,
        cancel_check: Callable[[], bool] | None = None,
    ) -> tuple[list[CompanyResult], ProviderError | None, float]:
        started = time.perf_counter()
        if _is_cancelled(cancel_check):
            return [], None, 0.0
        provider = self._provider(meta, enrichment=True)
        rows: list[CompanyResult] = []
        errors: list[ProviderError] = []
        for variant in _provider_query_variants(meta.provider_id, query_info):
            if _is_cancelled(cancel_check):
                return [], None, (time.perf_counter() - started) * 1000
            result_rows, _news, error = provider.search(variant, limit=limit)  # type: ignore[attr-defined]
            if _is_cancelled(cancel_check):
                return [], None, (time.perf_counter() - started) * 1000
            rows.extend(result_rows)
            if error and error.state != "empty":
                errors.append(error)
            if result_rows and _has_confident_result(result_rows):
                break
        return rows, errors[0] if errors else None, (time.perf_counter() - started) * 1000

    def _provider(self, meta: ProviderMeta, *, enrichment: bool) -> object:
        key = (meta.provider_id, enrichment)
        if key not in self._provider_instances:
            http = self.enrichment_http if enrichment else self.http
            self._provider_instances[key] = provider_for(meta, self.key_store, http, self.cache)
        return self._provider_instances[key]

    @staticmethod
    def _local_cache_key(query_info: QueryInfo, limit: int, region: str, scope: str) -> str:
        return f"{query_info.normalized}|{query_info.market_hint}|{region}|{scope}|{limit}"

    def _get_local_cache(self, key: str) -> SearchResponse | None:
        with self._cache_lock:
            cached = self._local_cache.get(key)
            if cached is None:
                return None
            created_at, response = cached
            if time.monotonic() - created_at > LOCAL_CACHE_TTL_SECONDS:
                self._local_cache.pop(key, None)
                return None
            self._local_cache.move_to_end(key)
            return _copy_response(response)

    def _put_local_cache(self, key: str, response: SearchResponse) -> None:
        with self._cache_lock:
            self._local_cache[key] = (time.monotonic(), _copy_response(response))
            self._local_cache.move_to_end(key)
            while len(self._local_cache) > LOCAL_CACHE_MAX_ITEMS:
                self._local_cache.popitem(last=False)

    @staticmethod
    def _log_timing(timing: SearchTiming, *, stage: str) -> None:
        log = logger.warning if timing.total_ms >= SLOW_SEARCH_MS else logger.debug
        log("search_timing stage=%s payload=%s", stage, timing.to_dict())

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
        advanced_enabled = self.settings.advanced_api_providers_enabled()
        for meta in self.registry.all():
            configured, masked = self.key_store.status(meta.key_name)
            if not meta.implemented:
                state = "disabled"
                message = meta.notes or "当前版本为 registry/stub，暂未接入真实请求。"
            elif meta.provider_id == "crawlergo_web_evidence":
                state, message = CrawlergoWebEvidenceProvider(crawlergo_path=self.settings.crawlergo_path()).dependency_status()
            elif not meta.requires_key and not meta.enabled_by_default and not advanced_enabled:
                state = "disabled"
                message = "Legacy / advanced provider 默认关闭；普通用户使用内置开源索引。"
            elif meta.requires_key and not meta.enabled_by_default and not advanced_enabled:
                state = "disabled"
                message = "Advanced API Provider 默认关闭；普通用户无需配置 API key。"
            elif meta.requires_key and not configured:
                state = "not_configured"
                message = f"未配置 {meta.key_name}，provider 将自动跳过。"
            else:
                state = "enabled"
                message = f"可用。Key 状态：{masked}。" if meta.requires_key else "可用。无需 API key。"
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
        advanced_enabled = self.settings.advanced_api_providers_enabled()
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
            elif meta.provider_id == "crawlergo_web_evidence":
                state, message = CrawlergoWebEvidenceProvider(crawlergo_path=self.settings.crawlergo_path()).dependency_status()
                status = ProviderStatus(meta.provider_id, meta.display_name, meta.category, state, message)
            elif meta.requires_key and not self.key_store.get(meta.key_name or ""):
                if not meta.enabled_by_default and not advanced_enabled:
                    status = ProviderStatus(
                        meta.provider_id,
                        meta.display_name,
                        meta.category,
                        "disabled",
                        "Advanced API Provider 默认关闭；普通用户无需配置 API key。",
                    )
                    statuses.append(status)
                    if progress_callback:
                        progress_callback(index, total, f"已完成 {meta.display_name}")
                    continue
                status = ProviderStatus(
                    meta.provider_id,
                    meta.display_name,
                    meta.category,
                    "not_configured",
                    f"未配置 {meta.key_name}，已跳过该增强数据源。",
                )
            else:
                provider = provider_for(meta, self.key_store, self.http, self.cache)
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
        advanced_enabled = self.settings.advanced_api_providers_enabled()
        implemented = [
            provider
            for provider in self.registry.implemented()
            if provider.enabled_by_default or advanced_enabled
        ]
        implemented_by_id = {provider.provider_id: provider for provider in implemented}
        region_priority = REGION_PROVIDER_PRIORITY.get(region_filter, REGION_PROVIDER_PRIORITY["all"])
        if advanced_enabled:
            region_priority = (*region_priority, *ADVANCED_PROVIDER_PRIORITY)
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
        "news": [item.to_dict() for item in response.news],
        "warnings": response.warnings,
        "errors": [
            {
                "provider_id": error.provider_id,
                "state": error.state,
                "message": error.message,
                "status_code": error.status_code,
                "retryable": error.retryable,
            }
            for error in response.errors
        ],
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
        "timing": response.timing.to_dict() if response.timing else None,
    }


def _is_cancelled(cancel_check: Callable[[], bool] | None) -> bool:
    return bool(cancel_check and cancel_check())


def _cancelled_local_response(
    query_info: QueryInfo,
    statuses: list[ProviderStatus],
    timing: SearchTiming,
    started: float,
) -> SearchResponse:
    timing.cancelled = True
    timing.total_ms = (time.perf_counter() - started) * 1000
    return SearchResponse(
        query=query_info.original.strip(),
        companies=[],
        news=[],
        statuses=statuses,
        timing=timing,
    )


def _cancelled_enrichment_response(base: SearchResponse, timing: SearchTiming) -> SearchResponse:
    timing.cancelled = True
    response = _copy_response(base)
    response.timing = timing
    return response


def _response_from_cache(data: dict[str, object]) -> SearchResponse:
    companies = [
        CompanyResult.from_dict(item)
        for item in data.get("companies", [])
        if isinstance(item, dict)
    ]
    news = [NewsItem.from_dict(item) for item in data.get("news", []) if isinstance(item, dict)]
    statuses = []
    for item in data.get("statuses", []):
        if not isinstance(item, dict):
            continue
        value = dict(item)
        checked = value.get("checked_at")
        if isinstance(checked, str):
            try:
                parsed = datetime.fromisoformat(checked.replace("Z", "+00:00"))
                value["checked_at"] = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            except ValueError:
                value["checked_at"] = datetime.now(UTC)
        statuses.append(ProviderStatus(**value))
    errors = []
    for item in data.get("errors", []):
        if isinstance(item, dict):
            errors.append(
                ProviderError(
                    str(item.get("provider_id") or ""),
                    item.get("state") or "failed",
                    str(item.get("message") or ""),
                    item.get("status_code"),
                    bool(item.get("retryable") or False),
                )
            )
    timing_data = data.get("timing")
    timing = SearchTiming(**timing_data) if isinstance(timing_data, dict) else None
    return SearchResponse(
        query=str(data.get("query") or ""),
        companies=companies,
        news=news,
        statuses=statuses,
        grouped_results=group_companies(companies),
        warnings=[str(item) for item in data.get("warnings", []) if item],
        errors=errors,
        from_cache=True,
        timing=timing,
    )


def _copy_response(response: SearchResponse | None) -> SearchResponse:
    if response is None:
        raise ValueError("response is required")
    return SearchResponse(
        query=response.query,
        companies=[CompanyResult.from_dict(item.to_dict()) for item in response.companies],
        news=[NewsItem.from_dict(item.to_dict()) for item in response.news],
        statuses=list(response.statuses),
        grouped_results={key: list(rows) for key, rows in response.grouped_results.items()},
        warnings=list(response.warnings),
        errors=list(response.errors),
        from_cache=response.from_cache,
        updated_at=response.updated_at,
        timing=SearchTiming(**response.timing.to_dict()) if response.timing else None,
    )


def _merge_search_responses(
    local: SearchResponse,
    enrichment: SearchResponse,
    query_info: QueryInfo,
    limit: int,
) -> SearchResponse:
    dedup_started = time.perf_counter()
    companies = rank_and_dedupe_companies([*local.companies, *enrichment.companies], query_info)[:limit]
    dedup_ms = (time.perf_counter() - dedup_started) * 1000
    timing = enrichment.timing or SearchTiming(query=query_info.original.strip())
    timing.dedup_ms = dedup_ms
    timing.result_count = len(companies)
    return SearchResponse(
        query=query_info.original.strip(),
        companies=companies,
        news=[],
        statuses=[*local.statuses, *enrichment.statuses],
        grouped_results=group_companies(companies),
        warnings=[*local.warnings, *enrichment.warnings],
        errors=[*local.errors, *enrichment.errors],
        from_cache=local.from_cache or enrichment.from_cache,
        timing=timing,
    )


def _dedupe_news(news: list[NewsItem]) -> list[NewsItem]:
    deduped: dict[str, NewsItem] = {}
    for item in news:
        key = item.dedupe_key()
        if key not in deduped:
            deduped[key] = item
    return sorted(deduped.values(), key=lambda item: item.published_at, reverse=True)


def _group_companies(companies: list[CompanyResult]) -> dict[str, list[CompanyResult]]:
    return group_companies(companies)


def _provider_query_variants(provider_id: str, query_info: QueryInfo) -> list[str]:
    variants = list(query_info.variants) or [query_info.original]
    if provider_id == "nasdaq_directory":
        preferred = [query_info.symbol, query_info.upper, query_info.original, *variants]
    elif provider_id in {"fmp", "alpha_vantage"}:
        preferred = [query_info.symbol, query_info.original, *variants]
    elif provider_id == "marketaux":
        preferred = [query_info.symbol, query_info.normalized_no_suffix, query_info.original, *variants]
    elif provider_id == "gleif":
        preferred = [
            query_info.normalized_no_suffix if len(query_info.normalized_no_suffix) >= 4 else "",
            query_info.original if len(query_info.original.strip()) >= 4 else "",
            *[variant for variant in variants if len(variant.strip()) >= 4],
        ]
    else:
        preferred = [query_info.normalized_no_suffix, query_info.original, *variants]
    deduped: list[str] = []
    seen: set[str] = set()
    for item in preferred:
        cleaned = (item or "").strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            deduped.append(cleaned)
        if len(deduped) >= 8:
            break
    return deduped


def _has_confident_result(companies: list[CompanyResult]) -> bool:
    return any(company.match_score >= 92 for company in companies)
