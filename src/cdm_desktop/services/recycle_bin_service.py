from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from cdm_desktop.db.models import (
    Alert,
    Company,
    Event,
    EventEvidence,
    RecycleBinItem,
    WatchlistItem,
    utc_now,
)
from cdm_desktop.db.repositories import RecycleBinRepository, WatchlistRepository, loads_json

RECYCLE_TYPE_EVENT = "event"
RECYCLE_TYPE_ALERT = "alert"
RECYCLE_TYPE_WATCHLIST = "watchlist_company"


@dataclass(frozen=True)
class RecycleBinCardData:
    id: int
    item_type: str
    entity_id: int
    title: str
    description: str
    deleted_at_text: str


class RecycleBinService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = RecycleBinRepository(session)

    def move_event_to_recycle(self, event_id: int) -> None:
        event = self.session.get(Event, event_id)
        if event is None:
            raise ValueError(f"Event not found: {event_id}")
        event.deleted_at = utc_now()
        linked_alerts = list(self.session.scalars(select(Alert).where(Alert.event_id == event_id)))
        linked_alert_ids: list[int] = []
        for alert in linked_alerts:
            alert.deleted_at = alert.deleted_at or event.deleted_at
            linked_alert_ids.append(alert.id)
        company = self.session.get(Company, event.company_id)
        self.repo.create_or_reopen(
            item_type=RECYCLE_TYPE_EVENT,
            entity_id=event.id,
            title=event.title,
            description=f"{company.name if company else '公司'} · 事件",
            metadata={"linked_alert_ids": linked_alert_ids},
        )

    def move_alert_to_recycle(self, alert_id: int) -> None:
        alert = self.session.get(Alert, alert_id)
        if alert is None:
            raise ValueError(f"Alert not found: {alert_id}")
        alert.deleted_at = utc_now()
        company = self.session.get(Company, alert.company_id)
        self.repo.create_or_reopen(
            item_type=RECYCLE_TYPE_ALERT,
            entity_id=alert.id,
            title=alert.title,
            description=f"{company.name if company else '公司'} · 告警",
            metadata={"event_id": alert.event_id},
        )

    def move_watchlist_company_to_recycle(self, company_id: int) -> None:
        company = self.session.get(Company, company_id)
        if company is None:
            raise ValueError(f"Company not found: {company_id}")
        WatchlistRepository(self.session).remove(company_id)
        self.repo.create_or_reopen(
            item_type=RECYCLE_TYPE_WATCHLIST,
            entity_id=company.id,
            title=company.name,
            description="自选公司 · 历史事件、告警和文档已保留",
            metadata={"ticker": company.ticker, "exchange": company.exchange},
        )

    def restore(self, recycle_item_id: int) -> None:
        item = self.repo.get(recycle_item_id)
        if item.item_type == RECYCLE_TYPE_EVENT:
            self._restore_event(item)
        elif item.item_type == RECYCLE_TYPE_ALERT:
            self._restore_alert(item)
        elif item.item_type == RECYCLE_TYPE_WATCHLIST:
            WatchlistRepository(self.session).add(item.entity_id)
        else:
            raise ValueError(f"Unsupported recycle type: {item.item_type}")
        self.repo.mark_restored(item.id)

    def permanently_delete(self, recycle_item_id: int) -> None:
        item = self.repo.get(recycle_item_id)
        if item.item_type == RECYCLE_TYPE_EVENT:
            self._permanently_delete_event(item.entity_id)
        elif item.item_type == RECYCLE_TYPE_ALERT:
            self._permanently_delete_alert(item.entity_id)
        elif item.item_type == RECYCLE_TYPE_WATCHLIST:
            self._clear_watchlist_item(item.entity_id)
        else:
            raise ValueError(f"Unsupported recycle type: {item.item_type}")
        self.repo.delete_item(item.id)

    def list_items(self, item_type: str | None = None) -> list[RecycleBinCardData]:
        cards: list[RecycleBinCardData] = []
        for item in self.repo.list(item_type=item_type):
            cards.append(
                RecycleBinCardData(
                    id=item.id,
                    item_type=item.item_type,
                    entity_id=item.entity_id,
                    title=item.title,
                    description=item.description or "",
                    deleted_at_text=item.deleted_at.strftime("%Y-%m-%d %H:%M"),
                )
            )
        return cards

    def _restore_event(self, item: RecycleBinItem) -> None:
        event = self.session.get(Event, item.entity_id)
        if event is None:
            raise ValueError("事件已不存在，无法恢复")
        event.deleted_at = None
        metadata = loads_json(item.metadata_json, {}) or {}
        linked_alert_ids = metadata.get("linked_alert_ids", [])
        if linked_alert_ids:
            for alert in self.session.scalars(select(Alert).where(Alert.id.in_(linked_alert_ids))):
                alert.deleted_at = None

    def _restore_alert(self, item: RecycleBinItem) -> None:
        alert = self.session.get(Alert, item.entity_id)
        if alert is None:
            raise ValueError("告警已不存在，无法恢复")
        event = self.session.get(Event, alert.event_id)
        if event and event.deleted_at is not None:
            event.deleted_at = None
        alert.deleted_at = None

    def _permanently_delete_event(self, event_id: int) -> None:
        self.session.execute(delete(EventEvidence).where(EventEvidence.event_id == event_id))
        self.session.execute(delete(Alert).where(Alert.event_id == event_id))
        self.session.execute(delete(Event).where(Event.id == event_id))

    def _permanently_delete_alert(self, alert_id: int) -> None:
        self.session.execute(delete(Alert).where(Alert.id == alert_id))

    def _clear_watchlist_item(self, company_id: int) -> None:
        item = self.session.scalar(select(WatchlistItem).where(WatchlistItem.company_id == company_id))
        if item:
            item.is_active = False
            item.removed_at = item.removed_at or utc_now()
