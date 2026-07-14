from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

ProviderCategory = Literal[
    "global",
    "registry",
    "financial",
    "news",
    "fallback",
    "external_link",
    "symbol_universe",
    "experimental",
    "web_evidence",
]
ProviderState = Literal[
    "available",
    "loading",
    "healthy",
    "degraded",
    "unavailable",
    "dependency_error",
    "source_changed",
    "timeout",
    "enabled",
    "not_configured",
    "disabled",
    "failed",
    "rate_limited",
    "quota_exceeded",
    "premium_endpoint",
    "invalid_key",
    "empty",
    "network_timeout",
    "dns_failure",
    "http_error",
    "parse_error",
    "provider_unavailable",
    "cache_miss",
    "dependency_missing",
    "index_missing",
    "index_corrupted",
]


@dataclass(frozen=True)
class ApiKeyDefinition:
    key_name: str
    label: str
    provider_id: str
    registration_url: str
    help_text: str


@dataclass(frozen=True)
class ProviderMeta:
    provider_id: str
    display_name: str
    category: ProviderCategory
    coverage: str
    purpose: str
    requires_key: bool
    key_name: str | None
    free_tier: str
    registration_url: str
    implemented: bool
    enabled_by_default: bool = True
    notes: str = ""


@dataclass
class ProviderStatus:
    provider_id: str
    display_name: str
    category: ProviderCategory
    state: ProviderState
    message: str
    last_error: str = ""
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_checked_at: str = ""
    last_success_at: str = ""
    last_error_at: str = ""
    last_error_type: str = ""
    last_error_message: str = ""
    consecutive_failures: int = 0
    disabled_until: str = ""
    average_latency_ms: int = 0


@dataclass
class CompanyResult:
    name: str
    provider: str
    provider_id: str
    id: str = ""
    category: str = "company"
    display_name: str = ""
    symbol: str = ""
    exchange: str = ""
    market: str = ""
    country: str = ""
    lei: str = ""
    wikidata_id: str = ""
    wikipedia_url: str = ""
    jurisdiction: str = ""
    company_number: str = ""
    registry_number: str = ""
    legal_name: str = ""
    description: str = ""
    website: str = ""
    aliases: list[str] = field(default_factory=list)
    source_url: str = ""
    match_reason: str = ""
    match_score: int = 0
    updated_at: str = ""
    added_at: str = ""
    last_refreshed_at: str = ""
    last_status: str = ""
    from_cache: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def dedupe_key(self) -> str:
        if self.lei:
            return f"lei:{self.lei.upper()}"
        if self.symbol and self.exchange:
            return f"symbol:{self.symbol.upper()}:{self.exchange.upper()}"
        if self.company_number and self.jurisdiction:
            return f"registry:{self.jurisdiction.lower()}:{self.company_number.lower()}"
        if self.wikidata_id:
            return f"wikidata:{self.wikidata_id.upper()}"
        if self.provider_id and (self.symbol or self.lei or self.company_number):
            return f"provider:{self.provider_id}:{self.symbol or self.lei or self.company_number}".lower()
        return f"name:{self.name.strip().lower()}:{self.provider_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "provider": self.provider,
            "provider_id": self.provider_id,
            "id": self.id,
            "category": self.category,
            "display_name": self.display_name,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "market": self.market,
            "country": self.country,
            "lei": self.lei,
            "wikidata_id": self.wikidata_id,
            "wikipedia_url": self.wikipedia_url,
            "jurisdiction": self.jurisdiction,
            "company_number": self.company_number,
            "registry_number": self.registry_number,
            "legal_name": self.legal_name,
            "description": self.description,
            "website": self.website,
            "aliases": self.aliases,
            "source_url": self.source_url,
            "match_reason": self.match_reason,
            "match_score": self.match_score,
            "updated_at": self.updated_at,
            "added_at": self.added_at,
            "last_refreshed_at": self.last_refreshed_at,
            "last_status": self.last_status,
            "from_cache": self.from_cache,
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompanyResult:
        return cls(
            name=str(data.get("name") or ""),
            provider=str(data.get("provider") or ""),
            provider_id=str(data.get("provider_id") or ""),
            id=str(data.get("id") or ""),
            category=str(data.get("category") or "company"),
            display_name=str(data.get("display_name") or ""),
            symbol=str(data.get("symbol") or ""),
            exchange=str(data.get("exchange") or ""),
            market=str(data.get("market") or ""),
            country=str(data.get("country") or ""),
            lei=str(data.get("lei") or ""),
            wikidata_id=str(data.get("wikidata_id") or ""),
            wikipedia_url=str(data.get("wikipedia_url") or ""),
            jurisdiction=str(data.get("jurisdiction") or ""),
            company_number=str(data.get("company_number") or ""),
            registry_number=str(data.get("registry_number") or ""),
            legal_name=str(data.get("legal_name") or ""),
            description=str(data.get("description") or ""),
            website=str(data.get("website") or ""),
            aliases=[str(item) for item in data.get("aliases", []) if item],
            source_url=str(data.get("source_url") or ""),
            match_reason=str(data.get("match_reason") or ""),
            match_score=int(data.get("match_score") or 0),
            updated_at=str(data.get("updated_at") or ""),
            added_at=str(data.get("added_at") or ""),
            last_refreshed_at=str(data.get("last_refreshed_at") or ""),
            last_status=str(data.get("last_status") or ""),
            from_cache=bool(data.get("from_cache") or False),
            raw=dict(data.get("raw") or {}),
        )


@dataclass
class NewsItem:
    title: str
    provider: str
    id: str = ""
    provider_id: str = ""
    source: str = ""
    published_at: str = ""
    url: str = ""
    snippet: str = ""
    image_url: str = ""
    language: str = ""
    country: str = ""
    sentiment_score: float | None = None
    entities: list[dict[str, Any]] = field(default_factory=list)
    from_cache: bool = False
    relevance_score: int = 0

    def dedupe_key(self) -> str:
        if self.url:
            return f"url:{self.url.strip().lower()}"
        if self.title:
            return f"title:{self.source.lower()}:{self.title.strip().lower()}"
        return f"id:{self.provider_id}:{self.id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "provider": self.provider,
            "provider_id": self.provider_id,
            "source": self.source,
            "published_at": self.published_at,
            "url": self.url,
            "snippet": self.snippet,
            "image_url": self.image_url,
            "language": self.language,
            "country": self.country,
            "sentiment_score": self.sentiment_score,
            "entities": self.entities,
            "from_cache": self.from_cache,
            "relevance_score": self.relevance_score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NewsItem:
        sentiment = data.get("sentiment_score")
        return cls(
            id=str(data.get("id") or ""),
            title=str(data.get("title") or ""),
            provider=str(data.get("provider") or ""),
            provider_id=str(data.get("provider_id") or ""),
            source=str(data.get("source") or ""),
            published_at=str(data.get("published_at") or ""),
            url=str(data.get("url") or ""),
            snippet=str(data.get("snippet") or ""),
            image_url=str(data.get("image_url") or ""),
            language=str(data.get("language") or ""),
            country=str(data.get("country") or ""),
            sentiment_score=float(sentiment) if sentiment not in (None, "") else None,
            entities=[dict(item) for item in data.get("entities", []) if isinstance(item, dict)],
            from_cache=bool(data.get("from_cache") or False),
            relevance_score=int(data.get("relevance_score") or 0),
        )


@dataclass
class ExternalSourceLink:
    id: str
    title: str
    description: str
    url: str
    provider: str
    provider_type: str
    open_mode: str
    compliance_note: str
    symbol: str = ""
    market: str = ""
    created_at: str = ""
    is_direct_stock_link: bool = False


@dataclass
class CompanyProfile:
    schema_version: int = 4
    id: str = ""
    display_name: str = ""
    legal_name: str = ""
    short_name: str = ""
    aliases: list[str] = field(default_factory=list)
    logo_url: str = ""
    company_type: str = ""
    entity_type: str = ""
    symbol: str = ""
    normalized_symbol: str = ""
    exchange: str = ""
    market: str = ""
    region: str = ""
    instrument_type: str = ""
    is_listed: bool | None = None
    lei: str = ""
    registration_number: str = ""
    company_number: str = ""
    registry_number: str = ""
    jurisdiction: str = ""
    registration_status: str = ""
    entity_status: str = ""
    wikidata_id: str = ""
    wikipedia_url: str = ""
    website: str = ""
    official_source_url: str = ""
    source_urls: list[str] = field(default_factory=list)
    description: str = ""
    sector: str = ""
    industry: str = ""
    sub_industry: str = ""
    business_scope: str = ""
    country: str = ""
    country_code: str = ""
    price: str = ""
    previous_close: str = ""
    market_cap: str = ""
    updated_price_at: str = ""
    currency: str = ""
    ceo: str = ""
    employees: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    legal_address: str = ""
    registered_address: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    zip_code: str = ""
    image_url: str = ""
    listing_date: str = ""
    ipo_date: str = ""
    is_etf: bool | None = None
    is_actively_trading: bool | None = None
    is_adr: bool | None = None
    is_fund: bool | None = None
    provider_sources: list[str] = field(default_factory=list)
    field_sources: dict[str, str] = field(default_factory=dict)
    field_candidates: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    data_coverage: dict[str, Any] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    updated_at: str = ""
    from_cache: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompanyProfile:
        values: dict[str, Any] = {}
        list_fields = {"aliases", "source_urls", "provider_sources", "missing_fields"}
        dict_fields = {"field_sources", "field_candidates", "data_coverage", "raw"}
        bool_fields = {"is_listed", "is_etf", "is_fund", "is_adr", "is_actively_trading"}
        for name in cls.__dataclass_fields__:
            value = data.get(name)
            if name == "schema_version":
                values[name] = int(value or 1)
            elif name in list_fields:
                values[name] = list(value) if isinstance(value, (list, tuple)) else []
            elif name in dict_fields:
                values[name] = dict(value) if isinstance(value, dict) else {}
            elif name in bool_fields:
                if isinstance(value, bool):
                    values[name] = value
                elif isinstance(value, str) and value.strip().casefold() in {"true", "false"}:
                    values[name] = value.strip().casefold() == "true"
                else:
                    values[name] = None
            elif name == "from_cache":
                values[name] = bool(value)
            else:
                values[name] = str(value or "")
        if not values["postal_code"]:
            values["postal_code"] = values["zip_code"]
        if not values["zip_code"]:
            values["zip_code"] = values["postal_code"]
        return cls(**values)


@dataclass
class SearchTiming:
    query: str
    total_ms: float = 0.0
    normalize_ms: float = 0.0
    local_index_ms: float = 0.0
    fuzzy_ms: float = 0.0
    provider_ms: float = 0.0
    dedup_ms: float = 0.0
    ranking_ms: float = 0.0
    render_ms: float = 0.0
    provider_timings: dict[str, float] = field(default_factory=dict)
    cache_hit: bool = False
    cancelled: bool = False
    result_count: int = 0
    candidate_shortlist_size: int = 0
    fuzzy_candidate_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "total_ms": round(self.total_ms, 3),
            "normalize_ms": round(self.normalize_ms, 3),
            "local_index_ms": round(self.local_index_ms, 3),
            "fuzzy_ms": round(self.fuzzy_ms, 3),
            "provider_ms": round(self.provider_ms, 3),
            "dedup_ms": round(self.dedup_ms, 3),
            "ranking_ms": round(self.ranking_ms, 3),
            "render_ms": round(self.render_ms, 3),
            "provider_timings": {
                key: round(value, 3) for key, value in self.provider_timings.items()
            },
            "cache_hit": self.cache_hit,
            "cancelled": self.cancelled,
            "result_count": self.result_count,
            "candidate_shortlist_size": self.candidate_shortlist_size,
            "fuzzy_candidate_count": self.fuzzy_candidate_count,
        }


@dataclass
class SearchResponse:
    query: str
    companies: list[CompanyResult]
    news: list[NewsItem]
    statuses: list[ProviderStatus]
    grouped_results: dict[str, list[CompanyResult]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[ProviderError] = field(default_factory=list)
    from_cache: bool = False
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    timing: SearchTiming | None = None


@dataclass
class ProviderError:
    provider_id: str
    state: ProviderState
    message: str
    status_code: int | None = None
    retryable: bool = False
