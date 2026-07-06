from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from cdm_desktop.alerts.rules import alert_priority
from cdm_desktop.db.models import (
    Alert,
    Company,
    Document,
    DocumentCompanyMatch,
    Event,
    EventEvidence,
    Source,
    SourceRun,
    WatchlistItem,
)
from cdm_desktop.db.repositories import EventRepository, WatchlistRepository


@dataclass(frozen=True)
class HomeSummary:
    companies: int
    unread_alerts: int
    high_priority_alerts: int
    today_events: int
    sources_enabled: int
    sources_total: int
    last_scan_at: datetime | None


@dataclass(frozen=True)
class CompanyCardData:
    id: int
    name: str
    ticker: str
    exchange: str
    aliases_count: int
    country: str
    industry: str
    risk_priority: str
    unread_alerts: int
    new_event_count: int
    latest_event_title: str
    last_scanned_at: datetime | None
    source_status: str


@dataclass(frozen=True)
class EventCardData:
    id: int
    company_id: int
    company_name: str
    priority: str
    title: str
    event_type: str
    event_status: str
    confidence_score: float
    materiality_score: float
    created_at: datetime
    source_label: str
    evidence: str
    alert_id: int | None
    alert_status: str | None


@dataclass(frozen=True)
class AlertCardData:
    id: int
    event_id: int
    company_id: int
    company_name: str
    priority: str
    title: str
    message: str
    status: str
    confidence_score: float
    materiality_score: float
    created_at: datetime
    evidence: str


def get_home_summary(session: Session) -> HomeSummary:
    today_start = datetime.now(UTC).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
    last_scan_at = session.scalar(select(func.max(SourceRun.finished_at)))
    return HomeSummary(
        companies=session.scalar(
            select(func.count(WatchlistItem.id)).where(WatchlistItem.is_active.is_(True))
        )
        or 0,
        unread_alerts=session.scalar(
            select(func.count(Alert.id)).where(Alert.status == "unread", Alert.deleted_at.is_(None))
        )
        or 0,
        high_priority_alerts=session.scalar(
            select(func.count(Alert.id)).where(
                Alert.status == "unread",
                Alert.priority.in_(("P0", "P1")),
                Alert.deleted_at.is_(None),
            )
        )
        or 0,
        today_events=session.scalar(
            select(func.count(Event.id)).where(Event.created_at >= today_start, Event.deleted_at.is_(None))
        )
        or 0,
        sources_enabled=session.scalar(select(func.count(Source.id)).where(Source.enabled.is_(True))) or 0,
        sources_total=session.scalar(select(func.count(Source.id))) or 0,
        last_scan_at=last_scan_at,
    )


def get_company_cards(session: Session, query: str = "", limit: int = 50) -> list[CompanyCardData]:
    companies = WatchlistRepository(session).list_active(query=query, limit=limit)
    cards: list[CompanyCardData] = []
    last_scan_at = session.scalar(select(func.max(SourceRun.finished_at)))
    for company in companies:
        latest_event = session.scalar(
            select(Event)
            .where(Event.company_id == company.id, Event.deleted_at.is_(None))
            .order_by(Event.created_at.desc())
            .limit(1)
        )
        unread_alerts = session.scalar(
            select(func.count(Alert.id)).where(
                Alert.company_id == company.id,
                Alert.status == "unread",
                Alert.deleted_at.is_(None),
            )
        ) or 0
        new_event_count = session.scalar(
            select(func.count(Event.id)).where(
                Event.company_id == company.id,
                Event.created_at >= datetime.now(UTC).replace(tzinfo=None) - timedelta(days=7),
                Event.deleted_at.is_(None),
            )
        ) or 0
        highest_priority = session.scalar(
            select(Alert.priority)
            .where(Alert.company_id == company.id, Alert.status == "unread")
            .where(Alert.deleted_at.is_(None))
            .order_by(Alert.priority.asc())
            .limit(1)
        )
        if not highest_priority and latest_event:
            highest_priority = alert_priority(latest_event.materiality_score, latest_event.confidence_score)
        cards.append(
            CompanyCardData(
                id=company.id,
                name=company.name,
                ticker=company.ticker or "",
                exchange=company.exchange or "",
                aliases_count=len(company.aliases),
                country=company.country or "",
                industry=company.industry or "",
                risk_priority=highest_priority or "P3",
                unread_alerts=unread_alerts,
                new_event_count=new_event_count,
                latest_event_title=latest_event.title if latest_event else "暂无重大事件",
                last_scanned_at=last_scan_at,
                source_status="已采集" if last_scan_at else "未采集",
            )
        )
    return cards


def get_event_cards(
    session: Session,
    *,
    company_id: int | None = None,
    event_type: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    query: str = "",
    date_range: str = "all",
    limit: int = 200,
) -> list[EventCardData]:
    stmt = select(Event).where(Event.deleted_at.is_(None)).order_by(Event.created_at.desc()).limit(limit)
    if company_id:
        stmt = stmt.where(Event.company_id == company_id)
    if event_type:
        stmt = stmt.where(Event.event_type == event_type)
    if status:
        stmt = stmt.where(Event.event_status == status)
    if query:
        like = f"%{query.strip()}%"
        stmt = stmt.where(or_(Event.title.like(like), Event.summary.like(like), Event.event_type.like(like)))
    start_at = _date_range_start(date_range)
    if start_at:
        stmt = stmt.where(Event.created_at >= start_at)

    events = list(session.scalars(stmt))
    cards = [_event_card(session, event) for event in events]
    if priority:
        cards = [card for card in cards if card.priority == priority]
    return cards


def get_alert_cards(
    session: Session,
    *,
    inbox_filter: str = "unread",
    query: str = "",
    limit: int = 200,
) -> list[AlertCardData]:
    stmt = select(Alert).where(Alert.deleted_at.is_(None)).order_by(Alert.created_at.desc()).limit(limit)
    if inbox_filter == "unread":
        stmt = stmt.where(Alert.status == "unread")
    elif inbox_filter == "high":
        stmt = stmt.where(Alert.status == "unread", Alert.priority.in_(("P0", "P1")))
    elif inbox_filter == "processed":
        stmt = stmt.where(Alert.status == "acknowledged")
    elif inbox_filter == "ignored":
        stmt = stmt.where(Alert.status == "ignored")
    if query:
        like = f"%{query.strip()}%"
        stmt = stmt.where(or_(Alert.title.like(like), Alert.message.like(like)))
    return [_alert_card(session, alert) for alert in session.scalars(stmt)]


def company_related_sources(session: Session, company_id: int) -> list[Source]:
    source_ids = (
        select(Document.source_id)
        .join(DocumentCompanyMatch, Document.id == DocumentCompanyMatch.document_id)
        .where(DocumentCompanyMatch.company_id == company_id, Document.source_id.is_not(None))
        .distinct()
    )
    return list(session.scalars(select(Source).where(Source.id.in_(source_ids)).order_by(Source.created_at.desc())))


def company_related_documents(session: Session, company_id: int, limit: int = 100) -> list[Document]:
    return list(
        session.scalars(
            select(Document)
            .join(DocumentCompanyMatch, Document.id == DocumentCompanyMatch.document_id)
            .where(DocumentCompanyMatch.company_id == company_id)
            .order_by(Document.created_at.desc())
            .limit(limit)
        )
    )


def company_recent_event_count(session: Session, company_id: int, days: int = 7) -> int:
    start = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    return (
        session.scalar(
            select(func.count(Event.id)).where(
                Event.company_id == company_id,
                Event.created_at >= start,
                Event.deleted_at.is_(None),
            )
        )
        or 0
    )


def company_highest_priority_event(session: Session, company_id: int) -> Event | None:
    events = EventRepository(session).list(company_id=company_id, limit=100)
    return max(events, key=lambda item: (item.materiality_score, item.confidence_score), default=None)


def _event_card(session: Session, event: Event) -> EventCardData:
    company = session.get(Company, event.company_id)
    evidence = session.scalar(
        select(EventEvidence.snippet).where(EventEvidence.event_id == event.id).order_by(EventEvidence.created_at).limit(1)
    )
    alert = session.scalar(
        select(Alert).where(Alert.event_id == event.id, Alert.deleted_at.is_(None)).order_by(Alert.created_at.desc()).limit(1)
    )
    document = session.get(Document, event.document_id)
    priority = alert.priority if alert else alert_priority(event.materiality_score, event.confidence_score)
    return EventCardData(
        id=event.id,
        company_id=event.company_id,
        company_name=company.name if company else f"公司 {event.company_id}",
        priority=priority,
        title=event.title,
        event_type=event.event_type,
        event_status=event.event_status,
        confidence_score=event.confidence_score,
        materiality_score=event.materiality_score,
        created_at=event.created_at,
        source_label=_source_label(document.url if document else ""),
        evidence=evidence or event.summary or "暂无证据片段",
        alert_id=alert.id if alert else None,
        alert_status=alert.status if alert else None,
    )


def _alert_card(session: Session, alert: Alert) -> AlertCardData:
    event = session.get(Event, alert.event_id)
    company = session.get(Company, alert.company_id)
    evidence = session.scalar(
        select(EventEvidence.snippet).where(EventEvidence.event_id == alert.event_id).order_by(EventEvidence.created_at).limit(1)
    )
    return AlertCardData(
        id=alert.id,
        event_id=alert.event_id,
        company_id=alert.company_id,
        company_name=company.name if company else f"公司 {alert.company_id}",
        priority=alert.priority,
        title=alert.title,
        message=alert.message,
        status=alert.status,
        confidence_score=event.confidence_score if event else 0,
        materiality_score=event.materiality_score if event else 0,
        created_at=alert.created_at,
        evidence=evidence or "暂无证据片段",
    )


def _source_label(url: str) -> str:
    if not url:
        return "本地文档"
    parsed = urlparse(url)
    return parsed.netloc or url


def _date_range_start(date_range: str) -> datetime | None:
    now = datetime.now(UTC).replace(tzinfo=None)
    if date_range == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if date_range == "7d":
        return now - timedelta(days=7)
    if date_range == "30d":
        return now - timedelta(days=30)
    return None
