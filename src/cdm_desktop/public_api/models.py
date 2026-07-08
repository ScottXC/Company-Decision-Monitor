from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

ProviderCategory = Literal["global", "registry", "financial", "news", "fallback", "external_link"]
ProviderState = Literal[
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
    checked_at: datetime = field(default_factory=datetime.utcnow)


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
    display_name: str = ""
    symbol: str = ""
    exchange: str = ""
    market: str = ""
    lei: str = ""
    wikidata_id: str = ""
    wikipedia_url: str = ""
    website: str = ""
    description: str = ""
    sector: str = ""
    industry: str = ""
    country: str = ""
    price: str = ""
    market_cap: str = ""
    currency: str = ""
    ceo: str = ""
    employees: str = ""
    phone: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    image_url: str = ""
    ipo_date: str = ""
    is_etf: str = ""
    is_actively_trading: str = ""
    is_adr: str = ""
    is_fund: str = ""
    provider_sources: list[str] = field(default_factory=list)
    field_sources: dict[str, str] = field(default_factory=dict)
    updated_at: str = ""
    from_cache: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "display_name": self.display_name,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "market": self.market,
            "lei": self.lei,
            "wikidata_id": self.wikidata_id,
            "wikipedia_url": self.wikipedia_url,
            "website": self.website,
            "description": self.description,
            "sector": self.sector,
            "industry": self.industry,
            "country": self.country,
            "price": self.price,
            "market_cap": self.market_cap,
            "currency": self.currency,
            "ceo": self.ceo,
            "employees": self.employees,
            "phone": self.phone,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "zip_code": self.zip_code,
            "image_url": self.image_url,
            "ipo_date": self.ipo_date,
            "is_etf": self.is_etf,
            "is_actively_trading": self.is_actively_trading,
            "is_adr": self.is_adr,
            "is_fund": self.is_fund,
            "provider_sources": self.provider_sources,
            "field_sources": self.field_sources,
            "updated_at": self.updated_at,
            "from_cache": self.from_cache,
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompanyProfile:
        return cls(
            display_name=str(data.get("display_name") or ""),
            symbol=str(data.get("symbol") or ""),
            exchange=str(data.get("exchange") or ""),
            market=str(data.get("market") or ""),
            lei=str(data.get("lei") or ""),
            wikidata_id=str(data.get("wikidata_id") or ""),
            wikipedia_url=str(data.get("wikipedia_url") or ""),
            website=str(data.get("website") or ""),
            description=str(data.get("description") or ""),
            sector=str(data.get("sector") or ""),
            industry=str(data.get("industry") or ""),
            country=str(data.get("country") or ""),
            price=str(data.get("price") or ""),
            market_cap=str(data.get("market_cap") or ""),
            currency=str(data.get("currency") or ""),
            ceo=str(data.get("ceo") or ""),
            employees=str(data.get("employees") or ""),
            phone=str(data.get("phone") or ""),
            address=str(data.get("address") or ""),
            city=str(data.get("city") or ""),
            state=str(data.get("state") or ""),
            zip_code=str(data.get("zip_code") or ""),
            image_url=str(data.get("image_url") or ""),
            ipo_date=str(data.get("ipo_date") or ""),
            is_etf=str(data.get("is_etf") or ""),
            is_actively_trading=str(data.get("is_actively_trading") or ""),
            is_adr=str(data.get("is_adr") or ""),
            is_fund=str(data.get("is_fund") or ""),
            provider_sources=[str(item) for item in data.get("provider_sources", []) if item],
            field_sources={str(k): str(v) for k, v in dict(data.get("field_sources") or {}).items()},
            updated_at=str(data.get("updated_at") or ""),
            from_cache=bool(data.get("from_cache") or False),
            raw=dict(data.get("raw") or {}),
        )


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
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ProviderError:
    provider_id: str
    state: ProviderState
    message: str
    status_code: int | None = None
    retryable: bool = False
