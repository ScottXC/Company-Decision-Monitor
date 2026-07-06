from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal

SearchScope = Literal["all", "us", "hk", "a_share", "filings", "news"]
ProviderStatus = Literal["success", "partial", "failed", "disabled"]
SourceType = Literal[
    "public_json",
    "public_csv",
    "public_txt",
    "public_xlsx",
    "public_html",
    "rss",
    "filing",
]


@dataclass(frozen=True)
class CompanySearchCandidate:
    name: str
    legal_name: str = ""
    ticker: str = ""
    exchange: str = ""
    market: str = ""
    country: str = ""
    industry: str = ""
    source_provider: str = ""
    source_url: str = ""
    source_type: SourceType = "public_json"
    match_reason: str = ""
    confidence_score: float = 0
    freshness: str = ""
    raw_payload_json: str = "{}"
    aliases: tuple[str, ...] = ()
    coverage_note: str = ""
    already_watchlisted: bool = False
    company_id: int | None = None
    contributing_providers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> CompanySearchCandidate:
        aliases = data.get("aliases") or ()
        providers = data.get("contributing_providers") or ()
        return cls(
            name=str(data.get("name") or ""),
            legal_name=str(data.get("legal_name") or ""),
            ticker=str(data.get("ticker") or ""),
            exchange=str(data.get("exchange") or ""),
            market=str(data.get("market") or ""),
            country=str(data.get("country") or ""),
            industry=str(data.get("industry") or ""),
            source_provider=str(data.get("source_provider") or ""),
            source_url=str(data.get("source_url") or ""),
            source_type=str(data.get("source_type") or "public_json"),  # type: ignore[arg-type]
            match_reason=str(data.get("match_reason") or ""),
            confidence_score=float(data.get("confidence_score") or 0),
            freshness=str(data.get("freshness") or ""),
            raw_payload_json=str(data.get("raw_payload_json") or "{}"),
            aliases=tuple(str(item) for item in aliases),  # type: ignore[union-attr]
            coverage_note=str(data.get("coverage_note") or ""),
            already_watchlisted=bool(data.get("already_watchlisted") or False),
            company_id=int(data["company_id"]) if data.get("company_id") else None,
            contributing_providers=tuple(str(item) for item in providers),  # type: ignore[union-attr]
        )


@dataclass(frozen=True)
class ProviderSearchResponse:
    provider_id: str
    status: ProviderStatus
    candidates: list[CompanySearchCandidate] = field(default_factory=list)
    error_message: str = ""
    fetched_at: datetime | None = None
    from_cache: bool = False


@dataclass(frozen=True)
class ProviderRefreshResult:
    provider_id: str
    status: ProviderStatus
    rows: int = 0
    error_message: str = ""
    fetched_at: datetime | None = None
    from_cache: bool = False


@dataclass(frozen=True)
class OnlineSearchResult:
    query: str
    scope: SearchScope
    candidates: list[CompanySearchCandidate]
    provider_responses: list[ProviderSearchResponse]
    from_cache: bool = False

