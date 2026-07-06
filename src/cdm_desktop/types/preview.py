from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SearchScope = Literal["all", "a_share", "hk", "us", "private", "industry"]


@dataclass(frozen=True)
class CompanyProfile:
    id: str
    name: str
    ticker: str | None = None
    exchange: str | None = None
    industry: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class WatchlistItem:
    company_id: str
    group_name: str = "默认分组"


@dataclass(frozen=True)
class NewsItem:
    title: str
    source: str | None = None
    published_at: str | None = None


@dataclass(frozen=True)
class FinancialMetric:
    name: str
    value: str | None = None
    unit: str | None = None


@dataclass(frozen=True)
class RiskSignal:
    title: str
    level: Literal["low", "medium", "high", "critical"] = "low"
    description: str | None = None
