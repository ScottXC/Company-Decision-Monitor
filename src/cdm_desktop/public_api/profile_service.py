from __future__ import annotations

from datetime import datetime

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.cache import ApiCache, cache_key
from cdm_desktop.public_api.http_client import PublicHttpClient
from cdm_desktop.public_api.key_store import ApiKeyStore
from cdm_desktop.public_api.models import CompanyProfile, CompanyResult, ProviderStatus
from cdm_desktop.public_api.providers import provider_for
from cdm_desktop.public_api.registry import ProviderRegistry
from cdm_desktop.public_api.search_service import PublicSearchService


class CompanyProfileService:
    def __init__(self, paths: AppPaths | None = None) -> None:
        self.registry = ProviderRegistry()
        self.key_store = ApiKeyStore(paths)
        self.cache = ApiCache(paths)
        self.http = PublicHttpClient()
        self.search_service = PublicSearchService(paths)

    def get_profile(self, company: CompanyResult) -> tuple[CompanyProfile | None, list[ProviderStatus]]:
        cache_params = {
            "symbol": company.symbol,
            "provider": company.provider_id,
            "lei": company.lei,
            "wikidata_id": company.wikidata_id,
            "name": company.name,
        }
        key = cache_key("company_profile", "merged", cache_params, company.name or company.symbol)
        cached = self.cache.get(key)
        if isinstance(cached, dict):
            profile = CompanyProfile.from_dict(cached)
            profile.from_cache = True
            return profile, [ProviderStatus("cache", "本地缓存", "fallback", "enabled", "公司详情来自本地缓存。")]

        statuses: list[ProviderStatus] = []
        profiles: list[CompanyProfile] = []
        for provider_id in self._provider_order(company):
            meta = self._meta(provider_id)
            if meta is None:
                continue
            if meta.requires_key and not self.key_store.get(meta.key_name or ""):
                statuses.append(ProviderStatus(meta.provider_id, meta.display_name, meta.category, "not_configured", f"未配置 {meta.key_name}，已跳过。"))
                continue
            provider = provider_for(meta, self.key_store, self.http, self.cache)
            profile, error = provider.profile(company)
            if error:
                statuses.append(ProviderStatus(meta.provider_id, meta.display_name, meta.category, error.state, error.message, str(error.status_code or "")))
                continue
            if profile:
                profiles.append(profile)
                statuses.append(ProviderStatus(meta.provider_id, meta.display_name, meta.category, "enabled", "已返回公司详情字段。"))

        if profiles:
            merged = _merge_profiles(company, profiles)
            self.cache.set(key, merged.to_dict(), ttl_seconds=21600)
            return merged, statuses

        stale = self.cache.get_stale(key)
        if isinstance(stale, dict):
            profile = CompanyProfile.from_dict(stale)
            profile.from_cache = True
            statuses.append(ProviderStatus("cache", "本地缓存", "fallback", "enabled", "网络失败，正在显示缓存详情。"))
            return profile, statuses

        if company.name or company.symbol:
            fallback = CompanyProfile(
                display_name=company.display_name or company.name or company.symbol,
                symbol=company.symbol,
                exchange=company.exchange,
                market=company.market,
                lei=company.lei,
                wikidata_id=company.wikidata_id,
                wikipedia_url=company.wikipedia_url,
                website=company.website,
                description=company.description,
                country=company.country,
                provider_sources=[company.provider_id] if company.provider_id else [],
                updated_at=_now(),
                raw={"search_result": company.raw},
            )
            return fallback, statuses
        return None, statuses

    def get_profile_by_name(self, name: str) -> tuple[CompanyProfile | None, list[ProviderStatus]]:
        response = self.search_service.search(name, limit=5)
        best = response.companies[0] if response.companies else None
        if not best:
            return None, response.statuses
        profile, statuses = self.get_profile(best)
        return profile, [*response.statuses, *statuses]

    def _provider_order(self, company: CompanyResult) -> list[str]:
        order: list[str] = []
        if company.symbol:
            order.extend(["fmp", "alpha_vantage"])
        if company.wikidata_id:
            order.append("wikidata")
        if company.lei:
            order.append("gleif")
        if not order and company.name:
            order.extend(["fmp", "alpha_vantage", "wikidata", "gleif"])
        return list(dict.fromkeys(order))

    def _meta(self, provider_id: str):
        return next((item for item in self.registry.all() if item.provider_id == provider_id), None)


def _merge_profiles(company: CompanyResult, profiles: list[CompanyProfile]) -> CompanyProfile:
    merged = CompanyProfile(
        display_name=company.display_name or company.name or company.legal_name or company.symbol,
        symbol=company.symbol,
        exchange=company.exchange,
        market=company.market,
        lei=company.lei,
        wikidata_id=company.wikidata_id,
        wikipedia_url=company.wikipedia_url,
        website=company.website,
        description=company.description,
        country=company.country,
        provider_sources=[],
        field_sources={},
        updated_at=_now(),
        raw={"search_result": company.raw},
    )
    for profile in profiles:
        source = profile.provider_sources[0] if profile.provider_sources else "provider"
        if source not in merged.provider_sources:
            merged.provider_sources.append(source)
        for field in [
            "display_name",
            "symbol",
            "exchange",
            "market",
            "lei",
            "wikidata_id",
            "wikipedia_url",
            "website",
            "description",
            "sector",
            "industry",
            "country",
            "price",
            "market_cap",
            "currency",
            "ceo",
            "employees",
            "phone",
            "address",
            "city",
            "state",
            "zip_code",
            "image_url",
            "ipo_date",
            "is_etf",
            "is_actively_trading",
            "is_adr",
            "is_fund",
        ]:
            if not getattr(merged, field) and getattr(profile, field):
                setattr(merged, field, getattr(profile, field))
                merged.field_sources[field] = source
        merged.raw.update(profile.raw)
    if not merged.provider_sources and company.provider_id:
        merged.provider_sources.append(company.provider_id)
    return merged


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
