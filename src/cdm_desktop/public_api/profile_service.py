from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.cache import ApiCache, cache_key
from cdm_desktop.public_api.data_quality import (
    is_meaningful_value,
    missing_profile_fields,
    normalize_profile_value,
    profile_coverage,
)
from cdm_desktop.public_api.http_client import PublicHttpClient
from cdm_desktop.public_api.key_store import ApiKeyStore
from cdm_desktop.public_api.models import (
    CompanyProfile,
    CompanyResult,
    ProviderError,
    ProviderStatus,
)
from cdm_desktop.public_api.provider_health import utc_timestamp
from cdm_desktop.public_api.providers import provider_for
from cdm_desktop.public_api.query import normalize_query
from cdm_desktop.public_api.registry import ProviderRegistry
from cdm_desktop.public_api.search_service import PublicSearchService
from cdm_desktop.public_api.settings_store import PublicApiSettingsStore

PROFILE_SCHEMA_VERSION = 4
PROFILE_CACHE_TTL_SECONDS = 21600


class CompanyProfileService:
    def __init__(self, paths: AppPaths | None = None) -> None:
        self.registry = ProviderRegistry()
        self.key_store = ApiKeyStore(paths)
        self.cache = ApiCache(paths)
        self.http = PublicHttpClient()
        self.search_service = PublicSearchService(paths)
        self.settings = PublicApiSettingsStore(paths)

    def get_immediate_profile(self, company: CompanyResult) -> CompanyProfile:
        """Return search-result and bundled-index fields without a network request."""
        base = _profile_from_company(company)
        meta = self._meta("symbol_universe")
        if not meta or not company.symbol:
            return base
        provider = provider_for(meta, self.key_store, self.http, self.cache)
        local, _error = provider.profile(company)
        return _merge_profiles(company, [base, local] if local else [base])

    def get_profile(self, company: CompanyResult) -> tuple[CompanyProfile | None, list[ProviderStatus]]:
        key = self._profile_cache_key(company)
        cached = self.cache.get(key)
        if isinstance(cached, dict) and int(cached.get("schema_version") or 1) == PROFILE_SCHEMA_VERSION:
            profile = CompanyProfile.from_dict(cached)
            profile.from_cache = True
            return profile, [
                ProviderStatus("cache", "本地缓存", "fallback", "enabled", "公司详情来自当前版本缓存。")
            ]

        profiles: list[CompanyProfile] = [self.get_immediate_profile(company)]
        statuses: list[ProviderStatus] = [
            ProviderStatus(
                "symbol_universe",
                "内置开源证券索引",
                "symbol_universe",
                "enabled",
                "已加载本地基础资料。",
            )
        ]
        provider_ids = [item for item in self._provider_order(company) if item != "symbol_universe"]
        with ThreadPoolExecutor(max_workers=min(3, max(1, len(provider_ids)))) as pool:
            futures = {}
            for provider_id in provider_ids:
                meta = self._meta(provider_id)
                if meta is None:
                    continue
                if meta.requires_key and not self.key_store.get(meta.key_name or ""):
                    statuses.append(
                        ProviderStatus(meta.provider_id, meta.display_name, meta.category, "not_configured", "高级数据源未启用。")
                    )
                    continue
                futures[pool.submit(self._fetch_profile, provider_id, company)] = meta
            for future in as_completed(futures):
                meta = futures[future]
                try:
                    profile, error = future.result()
                except Exception:  # noqa: BLE001
                    profile, error = None, ProviderError(meta.provider_id, "provider_unavailable", "该公开资料来源暂时不可用。")
                if error:
                    statuses.append(
                        ProviderStatus(meta.provider_id, meta.display_name, meta.category, error.state, error.message)
                    )
                elif profile:
                    profiles.append(profile)
                    field_count = len(profile.field_sources)
                    statuses.append(
                        ProviderStatus(
                            meta.provider_id,
                            meta.display_name,
                            meta.category,
                            "enabled",
                            f"已补充 {field_count} 个资料字段。",
                        )
                    )

        merged = _merge_profiles(company, profiles)
        if profile_coverage(merged).populated_fields:
            self.cache.set(key, merged.to_dict(), ttl_seconds=PROFILE_CACHE_TTL_SECONDS)
            return merged, statuses

        stale = self.cache.get_stale(key)
        if isinstance(stale, dict):
            profile = CompanyProfile.from_dict(stale)
            profile.from_cache = True
            statuses.append(ProviderStatus("cache", "本地缓存", "fallback", "enabled", "公开来源失败，正在显示旧缓存详情。"))
            return profile, statuses
        return merged, statuses

    def get_profile_by_name(self, name: str) -> tuple[CompanyProfile | None, list[ProviderStatus]]:
        response = self.search_service.search(name, limit=5)
        best = response.companies[0] if response.companies else None
        if not best:
            return None, response.statuses
        profile, statuses = self.get_profile(best)
        return profile, [*response.statuses, *statuses]

    def _fetch_profile(
        self,
        provider_id: str,
        company: CompanyResult,
    ) -> tuple[CompanyProfile | None, ProviderError | None]:
        meta = self._meta(provider_id)
        if meta is None:
            return None, ProviderError(provider_id, "provider_unavailable", "未知资料来源。")
        return provider_for(meta, self.key_store, self.http, self.cache).profile(company)

    def _provider_order(self, company: CompanyResult) -> list[str]:
        order = ["symbol_universe"]
        market_text = " ".join([company.market, company.exchange, company.country, company.symbol]).upper()
        if any(marker in market_text for marker in ("CN", "CHINA", "SH", "SZ", "HK", "HONG KONG")):
            order.append("akshare")
        order.extend(["wikidata", "gleif"])
        if self.settings.advanced_api_providers_enabled() and company.symbol:
            order.extend(["fmp", "alpha_vantage"])
        return list(dict.fromkeys(order))

    def _profile_cache_key(self, company: CompanyResult) -> str:
        params = {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "normalized_symbol": (company.symbol or "").upper().replace("-", "."),
            "exchange": company.exchange,
            "market": company.market,
            "lei": company.lei,
            "wikidata_id": company.wikidata_id,
            "normalized_name": normalize_query(company.legal_name or company.name),
            "provider_mode": "advanced" if self.settings.advanced_api_providers_enabled() else "open_source",
        }
        return cache_key("company_profile", "merged", params, company.name or company.symbol)

    def _meta(self, provider_id: str):
        return next((item for item in self.registry.all() if item.provider_id == provider_id), None)


def _profile_from_company(company: CompanyResult) -> CompanyProfile:
    raw = company.raw or {}
    profile = CompanyProfile(
        schema_version=PROFILE_SCHEMA_VERSION,
        id=company.id,
        display_name=company.display_name or company.name or company.legal_name or company.symbol,
        legal_name=company.legal_name,
        aliases=list(company.aliases),
        description=company.description,
        website=company.website,
        symbol=company.symbol,
        normalized_symbol=(company.symbol or "").upper().replace("-", "."),
        exchange=company.exchange,
        market=company.market,
        country=company.country,
        currency=str(raw.get("currency") or ""),
        instrument_type=str(raw.get("instrument_type") or ""),
        sector=str(raw.get("sector") or ""),
        industry=str(raw.get("industry") or ""),
        lei=company.lei,
        registration_number=company.company_number or company.registry_number,
        company_number=company.company_number,
        registry_number=company.registry_number,
        jurisdiction=company.jurisdiction,
        registration_status=str(raw.get("registration_status") or raw.get("status") or ""),
        entity_status=str(raw.get("entity_status") or ""),
        legal_address=str(raw.get("legal_address") or ""),
        registered_address=str(raw.get("registered_address") or ""),
        wikidata_id=company.wikidata_id,
        wikipedia_url=company.wikipedia_url,
        official_source_url=company.source_url,
        source_urls=[company.source_url] if company.source_url else [],
        provider_sources=[company.provider_id] if company.provider_id else [],
        updated_at=company.updated_at or utc_timestamp(),
        from_cache=company.from_cache,
        raw={"search_result": raw},
    )
    profile.field_sources = {
        field: company.provider_id
        for field in profile.__dataclass_fields__
        if is_meaningful_value(getattr(profile, field), field)
        and field not in {"raw", "field_sources", "provider_sources", "source_urls", "schema_version"}
        and company.provider_id
    }
    return profile


MERGE_FIELDS = tuple(
    name
    for name in CompanyProfile.__dataclass_fields__
    if name
    not in {
        "schema_version",
        "provider_sources",
        "field_sources",
        "field_candidates",
        "data_coverage",
        "missing_fields",
        "updated_at",
        "from_cache",
        "raw",
    }
)

FIELD_PRIORITY: dict[str, tuple[str, ...]] = {
    "price": ("fmp", "alpha_vantage", "akshare"),
    "previous_close": ("fmp", "alpha_vantage", "akshare"),
    "market_cap": ("fmp", "alpha_vantage", "akshare"),
    "description": ("official_website_evidence", "akshare", "wikidata", "fmp", "alpha_vantage"),
    "website": ("official_website_evidence", "akshare", "wikidata", "fmp", "alpha_vantage"),
    "sector": ("akshare", "symbol_universe", "fmp", "alpha_vantage", "wikidata"),
    "industry": ("akshare", "symbol_universe", "fmp", "alpha_vantage", "wikidata"),
    "legal_name": ("official_registry", "gleif", "official_website_evidence", "symbol_universe", "wikidata"),
    "lei": ("gleif",),
    "jurisdiction": ("official_registry", "gleif"),
    "registration_status": ("official_registry", "gleif"),
}

PROFILE_PRIORITY = {
    "official_registry": 100,
    "official_website_evidence": 95,
    "akshare": 90,
    "symbol_universe": 86,
    "fmp": 82,
    "alpha_vantage": 78,
    "gleif": 76,
    "wikidata": 62,
}


def _merge_profiles(company: CompanyResult, profiles: list[CompanyProfile | None]) -> CompanyProfile:
    merged = CompanyProfile(schema_version=PROFILE_SCHEMA_VERSION, updated_at=utc_timestamp())
    valid_profiles = [profile for profile in profiles if profile is not None]
    for profile in sorted(valid_profiles, key=_profile_priority, reverse=True):
        source = profile.provider_sources[0] if profile.provider_sources else "provider"
        for provider_source in profile.provider_sources:
            if provider_source not in merged.provider_sources:
                merged.provider_sources.append(provider_source)
        for field in MERGE_FIELDS:
            candidate = normalize_profile_value(getattr(profile, field), field)
            current = getattr(merged, field)
            current_source = merged.field_sources.get(field, "")
            if _should_use_field(field, current, candidate, source, current_source):
                if is_meaningful_value(current, field) and current != candidate:
                    merged.field_candidates.setdefault(field, []).append(
                        {"value": current, "provider": current_source}
                    )
                setattr(merged, field, candidate)
                merged.field_sources[field] = source
            elif is_meaningful_value(candidate, field) and current != candidate:
                merged.field_candidates.setdefault(field, []).append({"value": candidate, "provider": source})
        merged.source_urls.extend(url for url in profile.source_urls if url not in merged.source_urls)
        merged.raw.update(profile.raw)
        merged.from_cache = merged.from_cache or profile.from_cache
    if not merged.provider_sources and company.provider_id:
        merged.provider_sources.append(company.provider_id)
    coverage = profile_coverage(merged)
    merged.data_coverage = coverage.to_dict()
    merged.missing_fields = missing_profile_fields(merged)
    return merged


def _profile_priority(profile: CompanyProfile) -> int:
    source = profile.provider_sources[0] if profile.provider_sources else ""
    return PROFILE_PRIORITY.get(source, 50)


def _should_use_field(field: str, current: Any, candidate: Any, new_source: str, current_source: str) -> bool:
    if not is_meaningful_value(candidate, field):
        return False
    if not is_meaningful_value(current, field):
        return True
    if new_source == current_source:
        return isinstance(candidate, str) and isinstance(current, str) and len(candidate) > len(current)
    priority = FIELD_PRIORITY.get(field)
    if not priority:
        return False
    new_rank = priority.index(new_source) if new_source in priority else len(priority)
    old_rank = priority.index(current_source) if current_source in priority else len(priority)
    return new_rank < old_rank


def _valid_field_value(value: Any) -> bool:
    return is_meaningful_value(value)


def _now() -> str:
    return utc_timestamp()
