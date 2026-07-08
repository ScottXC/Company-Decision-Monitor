from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

ProviderCategory = Literal["global", "registry", "financial", "news", "fallback"]
ProviderState = Literal[
    "enabled",
    "not_configured",
    "disabled",
    "failed",
    "rate_limited",
    "invalid_key",
    "empty",
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
    category: str = "company"
    symbol: str = ""
    exchange: str = ""
    market: str = ""
    country: str = ""
    lei: str = ""
    jurisdiction: str = ""
    company_number: str = ""
    registry_number: str = ""
    legal_name: str = ""
    description: str = ""
    website: str = ""
    source_url: str = ""
    match_reason: str = ""
    match_score: int = 0
    updated_at: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def dedupe_key(self) -> str:
        if self.lei:
            return f"lei:{self.lei.upper()}"
        if self.symbol and self.exchange:
            return f"symbol:{self.symbol.upper()}:{self.exchange.upper()}"
        if self.company_number and self.jurisdiction:
            return f"registry:{self.jurisdiction.lower()}:{self.company_number.lower()}"
        return f"name:{self.name.strip().lower()}:{self.provider_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "provider": self.provider,
            "provider_id": self.provider_id,
            "category": self.category,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "market": self.market,
            "country": self.country,
            "lei": self.lei,
            "jurisdiction": self.jurisdiction,
            "company_number": self.company_number,
            "registry_number": self.registry_number,
            "legal_name": self.legal_name,
            "description": self.description,
            "website": self.website,
            "source_url": self.source_url,
            "match_reason": self.match_reason,
            "match_score": self.match_score,
            "updated_at": self.updated_at,
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompanyResult:
        return cls(
            name=str(data.get("name") or ""),
            provider=str(data.get("provider") or ""),
            provider_id=str(data.get("provider_id") or ""),
            category=str(data.get("category") or "company"),
            symbol=str(data.get("symbol") or ""),
            exchange=str(data.get("exchange") or ""),
            market=str(data.get("market") or ""),
            country=str(data.get("country") or ""),
            lei=str(data.get("lei") or ""),
            jurisdiction=str(data.get("jurisdiction") or ""),
            company_number=str(data.get("company_number") or ""),
            registry_number=str(data.get("registry_number") or ""),
            legal_name=str(data.get("legal_name") or ""),
            description=str(data.get("description") or ""),
            website=str(data.get("website") or ""),
            source_url=str(data.get("source_url") or ""),
            match_reason=str(data.get("match_reason") or ""),
            match_score=int(data.get("match_score") or 0),
            updated_at=str(data.get("updated_at") or ""),
            raw=dict(data.get("raw") or {}),
        )


@dataclass
class NewsItem:
    title: str
    provider: str
    source: str = ""
    published_at: str = ""
    url: str = ""
    snippet: str = ""
    language: str = ""


@dataclass
class SearchResponse:
    query: str
    companies: list[CompanyResult]
    news: list[NewsItem]
    statuses: list[ProviderStatus]
    from_cache: bool = False


@dataclass
class ProviderError:
    provider_id: str
    state: ProviderState
    message: str
    status_code: int | None = None
    retryable: bool = False
