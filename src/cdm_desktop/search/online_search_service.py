from __future__ import annotations

import asyncio
from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from cdm_desktop.db.models import Company, Source
from cdm_desktop.db.repositories import SettingsRepository, WatchlistRepository
from cdm_desktop.search.cache import OnlineSearchCache
from cdm_desktop.search.models import (
    CompanySearchCandidate,
    OnlineSearchResult,
    ProviderSearchResponse,
    SearchScope,
)
from cdm_desktop.search.provider_base import OnlineCompanySearchProvider
from cdm_desktop.search.providers import (
    HKEXNewsProvider,
    HKEXSecuritiesProvider,
    NasdaqSymbolDirectoryProvider,
    RSSNewsProvider,
    SECCompanyProvider,
    StockConnectProvider,
)
from cdm_desktop.search.ranking import dedupe_and_rank


class OnlineCompanySearchService:
    def __init__(
        self,
        session: Session,
        *,
        providers: list[OnlineCompanySearchProvider] | None = None,
    ) -> None:
        self.session = session
        settings = SettingsRepository(session)
        self.enabled = settings.get("online_search_enabled", "true") == "true"
        self.cache_ttl_hours = int(settings.get("online_search_cache_hours", "24") or "24")
        self.timeout_seconds = int(settings.get("online_search_timeout_seconds", "15") or "15")
        self.max_results = int(settings.get("online_search_max_results", "20") or "20")
        self.sec_user_agent = settings.get("online_search_sec_user_agent", "CompanyDecisionMonitor contact@example.com") or "CompanyDecisionMonitor contact@example.com"
        self.providers = providers if providers is not None else self._build_default_providers()
        self.cache = OnlineSearchCache(session, ttl_hours=self.cache_ttl_hours)

    def search(self, query: str, scope: SearchScope = "all", limit: int | None = None) -> OnlineSearchResult:
        query = query.strip()
        limit = limit or self.max_results
        if not self.enabled:
            return OnlineSearchResult(
                query,
                scope,
                [],
                [ProviderSearchResponse("online_search", "disabled", error_message="联网搜索已禁用。")],
            )
        if not query:
            return OnlineSearchResult(query, scope, [], [])

        cached = self.cache.get_search(query, scope)
        if cached:
            candidates, statuses = cached
            return OnlineSearchResult(
                query,
                scope,
                self._mark_watchlisted(candidates)[:limit],
                [
                    ProviderSearchResponse(
                        str(status.get("provider_id")),
                        str(status.get("status") or "success"),  # type: ignore[arg-type]
                        error_message=str(status.get("error_message") or ""),
                        from_cache=True,
                    )
                    for status in statuses
                ],
                from_cache=True,
            )

        responses = asyncio.run(self._search_async(query, scope, limit))
        candidates = dedupe_and_rank([candidate for response in responses for candidate in response.candidates])
        candidates = self._mark_watchlisted(candidates)[:limit]
        self.cache.put_search(query, scope, candidates, responses)
        return OnlineSearchResult(query, scope, candidates, responses)

    def refresh_reference_data(self) -> list[object]:
        return asyncio.run(self._refresh_async())

    async def _search_async(self, query: str, scope: SearchScope, limit: int) -> list[ProviderSearchResponse]:
        tasks = [provider.search(query, scope, limit) for provider in self.providers if not provider.requires_api_key]
        if not tasks:
            return []
        return list(await asyncio.gather(*tasks))

    async def _refresh_async(self) -> list[object]:
        tasks = [provider.refresh_reference_data() for provider in self.providers if not provider.requires_api_key]
        return list(await asyncio.gather(*tasks))

    def _build_default_providers(self) -> list[OnlineCompanySearchProvider]:
        settings = SettingsRepository(self.session)
        rss_urls = [
            source.url
            for source in self.session.scalars(select(Source).where(Source.enabled.is_(True), Source.source_type == "rss"))
        ]
        ir_urls = [
            source.url
            for source in self.session.scalars(
                select(Source).where(Source.enabled.is_(True), Source.source_type.in_(("webpage", "manual_url")))
            )
        ]
        providers: list[OnlineCompanySearchProvider] = []
        if settings.get("online_search_sec_enabled", "true") == "true":
            providers.append(SECCompanyProvider(user_agent=self.sec_user_agent, timeout_seconds=self.timeout_seconds))
        if settings.get("online_search_nasdaq_enabled", "true") == "true":
            providers.append(NasdaqSymbolDirectoryProvider(timeout_seconds=self.timeout_seconds))
        if settings.get("online_search_hkex_enabled", "true") == "true":
            providers.append(HKEXSecuritiesProvider(timeout_seconds=self.timeout_seconds))
        if settings.get("online_search_stock_connect_enabled", "true") == "true":
            providers.append(StockConnectProvider(timeout_seconds=self.timeout_seconds))
        if settings.get("online_search_hkexnews_enabled", "false") == "true":
            providers.append(HKEXNewsProvider())
        if settings.get("online_search_rss_enabled", "true") == "true":
            providers.append(RSSNewsProvider(rss_urls, timeout_seconds=self.timeout_seconds))
        if settings.get("online_search_ir_enabled", "true") == "true":
            from cdm_desktop.search.providers.company_ir_provider import CompanyIRProvider

            providers.append(CompanyIRProvider(ir_urls, timeout_seconds=self.timeout_seconds))
        return providers

    def _mark_watchlisted(self, candidates: list[CompanySearchCandidate]) -> list[CompanySearchCandidate]:
        active_ids = WatchlistRepository(self.session).active_company_ids()
        rows = list(self.session.scalars(select(Company)))
        by_ticker = {company.ticker.upper(): company for company in rows if company.ticker}
        by_name = {company.name.lower(): company for company in rows}
        marked = []
        for candidate in candidates:
            company = by_ticker.get(candidate.ticker.upper()) if candidate.ticker else by_name.get(candidate.name.lower())
            marked.append(
                replace(
                    candidate,
                    already_watchlisted=bool(company and company.id in active_ids),
                    company_id=company.id if company else candidate.company_id,
                )
            )
        return marked
