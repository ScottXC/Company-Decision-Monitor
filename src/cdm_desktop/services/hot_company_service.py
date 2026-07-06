from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cdm_desktop.alerts.rules import alert_priority
from cdm_desktop.db.models import Alert, Company, Document, DocumentCompanyMatch, Event
from cdm_desktop.db.repositories import WatchlistRepository
from cdm_desktop.search.models import CompanySearchCandidate


@dataclass(frozen=True)
class HotCompanyCandidate:
    name: str
    ticker: str = ""
    exchange: str = ""
    country: str = ""
    industry: str = ""
    aliases: tuple[str, ...] = ()
    hot_score: float = 0
    hot_level: str = "低"
    reasons: tuple[str, ...] = ()
    source: str = "local"
    already_watchlisted: bool = False
    company_id: int | None = None
    universe_id: int | None = None


class HotCompanyProvider(Protocol):
    def get_hot_companies(self, limit: int) -> list[HotCompanyCandidate]:
        ...


class LocalEventHotCompanyProvider:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_hot_companies(self, limit: int) -> list[HotCompanyCandidate]:
        since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
        active_ids = WatchlistRepository(self.session).active_company_ids()
        event_counts = dict(
            self.session.execute(
                select(Event.company_id, func.count(Event.id))
                .where(Event.created_at >= since, Event.deleted_at.is_(None))
                .group_by(Event.company_id)
            ).all()
        )
        if not event_counts:
            return []
        high_counts = defaultdict(int)
        for event in self.session.scalars(
            select(Event).where(Event.company_id.in_(event_counts.keys()), Event.deleted_at.is_(None))
        ):
            if alert_priority(event.materiality_score, event.confidence_score) in {"P0", "P1"}:
                high_counts[event.company_id] += 1
        alert_counts = dict(
            self.session.execute(
                select(Alert.company_id, func.count(Alert.id))
                .where(Alert.priority.in_(("P0", "P1")), Alert.deleted_at.is_(None))
                .group_by(Alert.company_id)
            ).all()
        )
        candidates: list[HotCompanyCandidate] = []
        for company_id, count in event_counts.items():
            company = self.session.get(Company, company_id)
            if company is None:
                continue
            high_priority_count = high_counts[company_id] + int(alert_counts.get(company_id, 0))
            score = _score(
                news_mentions=0,
                event_count=int(count),
                high_priority_event_count=high_priority_count,
                source_diversity=1,
                recency=1,
            )
            candidates.append(
                HotCompanyCandidate(
                    name=company.name,
                    ticker=company.ticker or "",
                    exchange=company.exchange or "",
                    country=company.country or "",
                    industry=company.industry or "",
                    aliases=tuple(alias.alias for alias in company.aliases),
                    hot_score=score,
                    hot_level=_hot_level(score),
                    reasons=_reasons(event_count=int(count), high_priority_count=high_priority_count, mention_count=0),
                    source="local_events",
                    already_watchlisted=company.id in active_ids,
                    company_id=company.id,
                )
            )
        return sorted(candidates, key=lambda item: item.hot_score, reverse=True)[:limit]


class DocumentMentionHotCompanyProvider:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_hot_companies(self, limit: int) -> list[HotCompanyCandidate]:
        since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
        rows = self.session.execute(
            select(
                DocumentCompanyMatch.company_id,
                func.count(DocumentCompanyMatch.id),
                func.count(func.distinct(Document.source_id)),
            )
            .join(Document, Document.id == DocumentCompanyMatch.document_id)
            .where(Document.created_at >= since)
            .group_by(DocumentCompanyMatch.company_id)
        ).all()
        active_ids = WatchlistRepository(self.session).active_company_ids()
        candidates: list[HotCompanyCandidate] = []
        for company_id, mentions, sources in rows:
            company = self.session.get(Company, company_id)
            if company is None:
                continue
            event_count = self.session.scalar(
                select(func.count(Event.id)).where(Event.company_id == company_id, Event.deleted_at.is_(None))
            ) or 0
            high_priority_count = self.session.scalar(
                select(func.count(Alert.id)).where(
                    Alert.company_id == company_id,
                    Alert.priority.in_(("P0", "P1")),
                    Alert.deleted_at.is_(None),
                )
            ) or 0
            score = _score(
                news_mentions=int(mentions),
                event_count=int(event_count),
                high_priority_event_count=int(high_priority_count),
                source_diversity=int(sources or 1),
                recency=1,
            )
            candidates.append(
                HotCompanyCandidate(
                    name=company.name,
                    ticker=company.ticker or "",
                    exchange=company.exchange or "",
                    country=company.country or "",
                    industry=company.industry or "",
                    aliases=tuple(alias.alias for alias in company.aliases),
                    hot_score=score,
                    hot_level=_hot_level(score),
                    reasons=_reasons(
                        event_count=int(event_count),
                        high_priority_count=int(high_priority_count),
                        mention_count=int(mentions),
                    ),
                    source="document_mentions",
                    already_watchlisted=company.id in active_ids,
                    company_id=company.id,
                )
            )
        return sorted(candidates, key=lambda item: item.hot_score, reverse=True)[:limit]


class HotCompanyService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.providers: tuple[HotCompanyProvider, ...] = (
            LocalEventHotCompanyProvider(session),
            DocumentMentionHotCompanyProvider(session),
        )

    def get_hot_companies(self, limit: int = 8) -> list[HotCompanyCandidate]:
        combined: dict[str, HotCompanyCandidate] = {}
        for provider in self.providers:
            for candidate in provider.get_hot_companies(limit):
                key = candidate.ticker.upper() if candidate.ticker else candidate.name.lower()
                existing = combined.get(key)
                if existing is None or candidate.hot_score > existing.hot_score:
                    combined[key] = candidate
        return sorted(combined.values(), key=lambda item: item.hot_score, reverse=True)[:limit]

    @staticmethod
    def to_search_candidate(candidate: HotCompanyCandidate) -> CompanySearchCandidate:
        return CompanySearchCandidate(
            name=candidate.name,
            ticker=candidate.ticker,
            exchange=candidate.exchange,
            country=candidate.country,
            industry=candidate.industry,
            aliases=candidate.aliases,
            market="本地热度",
            source_provider="本地公开资料统计",
            source_url="",
            source_type="public_json",
            match_reason="热门公司候选",
            confidence_score=candidate.hot_score,
            already_watchlisted=candidate.already_watchlisted,
            company_id=candidate.company_id,
        )


def _score(
    *,
    news_mentions: int,
    event_count: int,
    high_priority_event_count: int,
    source_diversity: int,
    recency: int,
) -> float:
    return min(
        100.0,
        0.40 * min(news_mentions * 15, 100)
        + 0.25 * min(event_count * 20, 100)
        + 0.20 * min(high_priority_event_count * 35, 100)
        + 0.10 * min(source_diversity * 25, 100)
        + 0.05 * min(recency * 100, 100),
    )


def _hot_level(score: float) -> str:
    if score >= 75:
        return "高"
    if score >= 45:
        return "中"
    return "低"


def _reasons(*, event_count: int, high_priority_count: int, mention_count: int) -> tuple[str, ...]:
    reasons: list[str] = []
    if mention_count:
        reasons.append("新闻提及较多")
    if event_count:
        reasons.append("事件较多")
    if high_priority_count:
        reasons.append("高优先级事件较多")
    if not reasons:
        reasons.append("最近被频繁提及")
    return tuple(reasons)
