from __future__ import annotations

from sqlalchemy.orm import Session

from cdm_desktop.alerts.rules import alert_priority
from cdm_desktop.db.models import Event
from cdm_desktop.db.repositories import AlertRepository


class AlertService:
    def create_for_event(self, session: Session, event: Event) -> None:
        repo = AlertRepository(session)
        if repo.find_by_event(event.id):
            return
        priority = alert_priority(event.materiality_score, event.confidence_score)
        repo.create(
            event_id=event.id,
            company_id=event.company_id,
            priority=priority,
            title=f"[{priority}] {event.title}",
            message=(
                f"{event.summary or event.title}\n"
                f"重大性评分：{event.materiality_score:.1f}；置信度评分：{event.confidence_score:.1f}"
            ),
            status="unread",
        )
