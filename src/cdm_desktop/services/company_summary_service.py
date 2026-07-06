from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cdm_desktop.alerts.rules import alert_priority
from cdm_desktop.db.models import Alert, Company, DocumentCompanyMatch, Event, SourceRun
from cdm_desktop.services.ui_query_service import company_highest_priority_event


@dataclass(frozen=True)
class CompanySummary:
    company_id: int
    name: str
    ticker: str
    exchange: str
    country: str
    industry: str
    unread_alert_count: int
    event_count: int
    recent_event_count: int
    document_count: int
    latest_event_title: str
    highest_priority: str
    highest_priority_label: str
    last_scan_at: datetime | None
    source_status: str


class CompanySummaryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_company_summary(self, company_id: int) -> CompanySummary:
        company = self.session.get(Company, company_id)
        if company is None:
            raise ValueError(f"Company not found: {company_id}")
        now = datetime.now(UTC).replace(tzinfo=None)
        seven_days_ago = now - timedelta(days=7)
        unread_alert_count = self.session.scalar(
            select(func.count(Alert.id)).where(
                Alert.company_id == company_id,
                Alert.status == "unread",
                Alert.deleted_at.is_(None),
            )
        ) or 0
        event_count = self.session.scalar(
            select(func.count(Event.id)).where(Event.company_id == company_id, Event.deleted_at.is_(None))
        ) or 0
        recent_event_count = self.session.scalar(
            select(func.count(Event.id)).where(
                Event.company_id == company_id,
                Event.created_at >= seven_days_ago,
                Event.deleted_at.is_(None),
            )
        ) or 0
        document_count = self.session.scalar(
            select(func.count(func.distinct(DocumentCompanyMatch.document_id))).where(
                DocumentCompanyMatch.company_id == company_id
            )
        ) or 0
        latest_event = self.session.scalar(
            select(Event)
            .where(Event.company_id == company_id, Event.deleted_at.is_(None))
            .order_by(Event.created_at.desc())
            .limit(1)
        )
        highest_event = company_highest_priority_event(self.session, company_id)
        highest_priority = (
            alert_priority(highest_event.materiality_score, highest_event.confidence_score)
            if highest_event
            else "P3"
        )
        last_scan_at = self.session.scalar(select(func.max(SourceRun.finished_at)))
        return CompanySummary(
            company_id=company.id,
            name=company.name,
            ticker=company.ticker or "",
            exchange=company.exchange or "",
            country=company.country or "",
            industry=company.industry or "",
            unread_alert_count=unread_alert_count,
            event_count=event_count,
            recent_event_count=recent_event_count,
            document_count=document_count,
            latest_event_title=latest_event.title if latest_event else "暂无重大事件",
            highest_priority=highest_priority,
            highest_priority_label=_priority_text(highest_priority),
            last_scan_at=last_scan_at,
            source_status="已采集" if last_scan_at else "未采集",
        )


def _priority_text(priority: str) -> str:
    return {
        "P0": "严重",
        "P1": "高",
        "P2": "中",
        "P3": "低",
    }.get(priority, "低")
