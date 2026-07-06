from __future__ import annotations

from typing import Any

import orjson
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from cdm_desktop.db.models import (
    Alert,
    AppSetting,
    AuditLog,
    Company,
    CompanyAlias,
    CompanyUniverse,
    Document,
    DocumentCompanyMatch,
    Event,
    EventEvidence,
    RecycleBinItem,
    Source,
    SourceRun,
    WatchlistItem,
    utc_now,
)


def dumps_json(value: Any) -> str:
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode("utf-8")


def loads_json(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    return orjson.loads(value)


class CompanyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, name: str, **kwargs: Any) -> Company:
        add_to_watchlist = bool(kwargs.pop("add_to_watchlist", True))
        company = Company(name=name.strip(), **kwargs)
        self.session.add(company)
        self.session.flush()
        self.add_alias(company.id, company.name, "chinese_name" if _has_cjk(company.name) else "english_name")
        if company.legal_name:
            self.add_alias(company.id, company.legal_name, "legal_name")
        if company.ticker:
            self.add_alias(company.id, company.ticker, "ticker")
        if add_to_watchlist:
            WatchlistRepository(self.session).add(company.id)
        return company

    def update(self, company_id: int, **kwargs: Any) -> Company:
        company = self.get(company_id)
        for key, value in kwargs.items():
            setattr(company, key, value)
        company.updated_at = utc_now()
        self.session.flush()
        return company

    def delete(self, company_id: int) -> None:
        company = self.get(company_id)
        self.session.delete(company)

    def get(self, company_id: int) -> Company:
        company = self.session.get(Company, company_id)
        if company is None:
            raise ValueError(f"Company not found: {company_id}")
        return company

    def list(self, query: str | None = None, search_scope: str = "all") -> list[Company]:
        stmt = select(Company).options(selectinload(Company.aliases)).order_by(Company.created_at.desc())
        query = (query or "").strip()
        if query:
            stmt = stmt.where(_company_search_condition(query, search_scope))
        return list(self.session.scalars(stmt))

    def add_alias(self, company_id: int, alias: str, alias_type: str = "other") -> CompanyAlias:
        alias = alias.strip()
        existing = self.session.scalar(
            select(CompanyAlias).where(
                and_(
                    CompanyAlias.company_id == company_id,
                    func.lower(CompanyAlias.alias) == alias.lower(),
                )
            )
        )
        if existing:
            return existing
        item = CompanyAlias(company_id=company_id, alias=alias, alias_type=alias_type)
        self.session.add(item)
        self.session.flush()
        return item

    def list_aliases(self, company_id: int) -> list[CompanyAlias]:
        return list(
            self.session.scalars(
                select(CompanyAlias)
                .where(CompanyAlias.company_id == company_id)
                .order_by(CompanyAlias.created_at.desc())
            )
        )


class CompanyUniverseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        *,
        name: str,
        legal_name: str | None = None,
        ticker: str | None = None,
        exchange: str | None = None,
        country: str | None = None,
        industry: str | None = None,
        aliases: list[str] | None = None,
        source: str = "online",
        source_provider: str | None = None,
        source_url: str | None = None,
        raw_payload_json: str | None = None,
        popularity_score: float = 0,
    ) -> CompanyUniverse:
        normalized_ticker = ticker.strip().upper() if ticker else None
        existing = self.session.scalar(
            select(CompanyUniverse).where(
                or_(
                    and_(CompanyUniverse.ticker.is_not(None), CompanyUniverse.ticker == normalized_ticker),
                    func.lower(CompanyUniverse.name) == name.strip().lower(),
                )
            )
        )
        if existing is None:
            existing = CompanyUniverse(name=name.strip())
            self.session.add(existing)
        existing.legal_name = legal_name
        existing.ticker = normalized_ticker
        existing.exchange = exchange
        existing.country = country
        existing.industry = industry
        existing.aliases_json = dumps_json(aliases or [])
        existing.source = source
        existing.source_provider = source_provider
        existing.source_url = source_url
        existing.raw_payload_json = raw_payload_json
        existing.popularity_score = popularity_score
        existing.last_seen_at = utc_now()
        existing.updated_at = utc_now()
        self.session.flush()
        return existing

    def list(self, limit: int = 500) -> list[CompanyUniverse]:
        return list(
            self.session.scalars(
                select(CompanyUniverse)
                .order_by(CompanyUniverse.popularity_score.desc(), CompanyUniverse.updated_at.desc())
                .limit(limit)
            )
        )

    def get(self, universe_id: int) -> CompanyUniverse:
        item = self.session.get(CompanyUniverse, universe_id)
        if item is None:
            raise ValueError(f"Company universe candidate not found: {universe_id}")
        return item


class WatchlistRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, company_id: int) -> WatchlistItem:
        existing = self.session.scalar(select(WatchlistItem).where(WatchlistItem.company_id == company_id))
        if existing:
            existing.is_active = True
            existing.removed_at = None
            existing.added_at = existing.added_at or utc_now()
            self.session.flush()
            return existing
        item = WatchlistItem(company_id=company_id, is_active=True, added_at=utc_now())
        self.session.add(item)
        self.session.flush()
        return item

    def remove(self, company_id: int) -> WatchlistItem:
        item = self.session.scalar(select(WatchlistItem).where(WatchlistItem.company_id == company_id))
        if item is None:
            item = WatchlistItem(company_id=company_id, is_active=False, added_at=utc_now(), removed_at=utc_now())
            self.session.add(item)
        else:
            item.is_active = False
            item.removed_at = utc_now()
        self.session.flush()
        return item

    def is_active(self, company_id: int) -> bool:
        return bool(
            self.session.scalar(
                select(WatchlistItem.id).where(
                    WatchlistItem.company_id == company_id,
                    WatchlistItem.is_active.is_(True),
                )
            )
        )

    def list_active(self, query: str = "", limit: int = 500) -> list[Company]:
        stmt = (
            select(Company)
            .join(WatchlistItem, WatchlistItem.company_id == Company.id)
            .options(selectinload(Company.aliases))
            .where(WatchlistItem.is_active.is_(True))
            .order_by(WatchlistItem.sort_order.asc(), WatchlistItem.added_at.desc())
            .limit(limit)
        )
        query = query.strip()
        if query:
            stmt = stmt.where(_company_search_condition(query, "all"))
        return list(self.session.scalars(stmt))

    def active_company_ids(self) -> set[int]:
        return set(
            self.session.scalars(
                select(WatchlistItem.company_id).where(WatchlistItem.is_active.is_(True))
            )
        )


class SourceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        name: str,
        source_type: str,
        url: str,
        config: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> Source:
        source = Source(
            name=name.strip(),
            source_type=source_type,
            url=url.strip(),
            config_json=dumps_json(config or {}),
            enabled=enabled,
        )
        self.session.add(source)
        self.session.flush()
        return source

    def update(self, source_id: int, **kwargs: Any) -> Source:
        source = self.get(source_id)
        if "config" in kwargs:
            source.config_json = dumps_json(kwargs.pop("config") or {})
        for key, value in kwargs.items():
            setattr(source, key, value)
        source.updated_at = utc_now()
        self.session.flush()
        return source

    def get(self, source_id: int) -> Source:
        source = self.session.get(Source, source_id)
        if source is None:
            raise ValueError(f"Source not found: {source_id}")
        return source

    def list(self, enabled_only: bool = False) -> list[Source]:
        stmt = select(Source).order_by(Source.created_at.desc())
        if enabled_only:
            stmt = stmt.where(Source.enabled.is_(True))
        return list(self.session.scalars(stmt))

    def create_run(self, source_id: int) -> SourceRun:
        run = SourceRun(source_id=source_id, status="running", started_at=utc_now())
        self.session.add(run)
        self.session.flush()
        return run

    def finish_run(
        self,
        run_id: int,
        status: str,
        documents_found: int = 0,
        documents_created: int = 0,
        error_message: str | None = None,
    ) -> SourceRun:
        run = self.session.get(SourceRun, run_id)
        if run is None:
            raise ValueError(f"Source run not found: {run_id}")
        run.status = status
        run.finished_at = utc_now()
        run.documents_found = documents_found
        run.documents_created = documents_created
        run.error_message = error_message
        source = self.get(run.source_id)
        source.last_run_at = run.finished_at
        self.session.flush()
        return run

    def latest_runs(self, limit: int = 50) -> list[SourceRun]:
        return list(
            self.session.scalars(select(SourceRun).order_by(SourceRun.started_at.desc()).limit(limit))
        )


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **kwargs: Any) -> Document:
        doc = Document(**kwargs)
        self.session.add(doc)
        self.session.flush()
        return doc

    def get(self, document_id: int) -> Document:
        document = self.session.get(Document, document_id)
        if document is None:
            raise ValueError(f"Document not found: {document_id}")
        return document

    def find_duplicate(self, canonical_url: str, content_hash: str) -> Document | None:
        return self.session.scalar(
            select(Document).where(
                or_(
                    Document.content_hash == content_hash,
                    and_(Document.canonical_url == canonical_url, Document.content_hash == content_hash),
                )
            )
        )

    def list(self, query: str | None = None, limit: int = 500) -> list[Document]:
        stmt = select(Document).order_by(Document.created_at.desc()).limit(limit)
        if query:
            like = f"%{query.strip()}%"
            stmt = stmt.where(or_(Document.title.like(like), Document.parsed_text.like(like), Document.url.like(like)))
        return list(self.session.scalars(stmt))

    def save_match(self, **kwargs: Any) -> DocumentCompanyMatch:
        existing = self.session.scalar(
            select(DocumentCompanyMatch).where(
                and_(
                    DocumentCompanyMatch.document_id == kwargs["document_id"],
                    DocumentCompanyMatch.company_id == kwargs["company_id"],
                    DocumentCompanyMatch.matched_text == kwargs["matched_text"],
                    DocumentCompanyMatch.match_type == kwargs["match_type"],
                )
            )
        )
        if existing:
            return existing
        match = DocumentCompanyMatch(**kwargs)
        self.session.add(match)
        self.session.flush()
        return match


class EventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **kwargs: Any) -> Event:
        event = Event(**kwargs)
        self.session.add(event)
        self.session.flush()
        return event

    def get(self, event_id: int) -> Event:
        event = self.session.get(Event, event_id)
        if event is None:
            raise ValueError(f"Event not found: {event_id}")
        return event

    def list(
        self,
        company_id: int | None = None,
        event_type: str | None = None,
        status: str | None = None,
        limit: int = 500,
    ) -> list[Event]:
        stmt = select(Event).where(Event.deleted_at.is_(None)).order_by(Event.created_at.desc()).limit(limit)
        if company_id:
            stmt = stmt.where(Event.company_id == company_id)
        if event_type:
            stmt = stmt.where(Event.event_type == event_type)
        if status:
            stmt = stmt.where(Event.event_status == status)
        return list(self.session.scalars(stmt))

    def find_existing(self, company_id: int, document_id: int, event_type: str, title: str) -> Event | None:
        return self.session.scalar(
            select(Event).where(
                and_(
                    Event.company_id == company_id,
                    Event.document_id == document_id,
                    Event.event_type == event_type,
                    Event.title == title,
                    Event.deleted_at.is_(None),
                )
            )
        )

    def add_evidence(self, **kwargs: Any) -> EventEvidence:
        evidence = EventEvidence(**kwargs)
        self.session.add(evidence)
        self.session.flush()
        return evidence

    def evidence_for_event(self, event_id: int) -> list[EventEvidence]:
        return list(
            self.session.scalars(
                select(EventEvidence).where(EventEvidence.event_id == event_id).order_by(EventEvidence.created_at)
            )
        )


class AlertRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **kwargs: Any) -> Alert:
        alert = Alert(**kwargs)
        self.session.add(alert)
        self.session.flush()
        return alert

    def find_by_event(self, event_id: int) -> Alert | None:
        return self.session.scalar(select(Alert).where(Alert.event_id == event_id, Alert.deleted_at.is_(None)))

    def list(self, status: str | None = None, limit: int = 500) -> list[Alert]:
        stmt = select(Alert).where(Alert.deleted_at.is_(None)).order_by(Alert.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(Alert.status == status)
        return list(self.session.scalars(stmt))

    def set_status(self, alert_id: int, status: str) -> Alert:
        alert = self.session.get(Alert, alert_id)
        if alert is None:
            raise ValueError(f"Alert not found: {alert_id}")
        alert.status = status
        if status == "acknowledged":
            alert.acknowledged_at = utc_now()
        if status == "ignored":
            alert.ignored_at = utc_now()
        self.session.flush()
        return alert


class RecycleBinRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_or_reopen(
        self,
        *,
        item_type: str,
        entity_id: int,
        title: str,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RecycleBinItem:
        item = self.session.scalar(
            select(RecycleBinItem).where(
                RecycleBinItem.item_type == item_type,
                RecycleBinItem.entity_id == entity_id,
                RecycleBinItem.status == "active",
            )
        )
        if item is None:
            item = RecycleBinItem(item_type=item_type, entity_id=entity_id, title=title)
            self.session.add(item)
        item.title = title
        item.description = description
        item.metadata_json = dumps_json(metadata or {})
        item.status = "active"
        item.deleted_at = utc_now()
        item.restored_at = None
        self.session.flush()
        return item

    def list(self, item_type: str | None = None, status: str = "active", limit: int = 500) -> list[RecycleBinItem]:
        stmt = select(RecycleBinItem).where(RecycleBinItem.status == status).order_by(RecycleBinItem.deleted_at.desc()).limit(limit)
        if item_type:
            stmt = stmt.where(RecycleBinItem.item_type == item_type)
        return list(self.session.scalars(stmt))

    def get(self, item_id: int) -> RecycleBinItem:
        item = self.session.get(RecycleBinItem, item_id)
        if item is None:
            raise ValueError(f"Recycle bin item not found: {item_id}")
        return item

    def mark_restored(self, item_id: int) -> RecycleBinItem:
        item = self.get(item_id)
        item.status = "restored"
        item.restored_at = utc_now()
        self.session.flush()
        return item

    def delete_item(self, item_id: int) -> None:
        item = self.get(item_id)
        self.session.delete(item)


class SettingsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, key: str, default: str | None = None) -> str | None:
        item = self.session.scalar(select(AppSetting).where(AppSetting.key == key))
        return item.value if item else default

    def set(self, key: str, value: str) -> AppSetting:
        item = self.session.scalar(select(AppSetting).where(AppSetting.key == key))
        if item is None:
            item = AppSetting(key=key, value=value)
            self.session.add(item)
        else:
            item.value = value
            item.updated_at = utc_now()
        self.session.flush()
        return item


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def log(self, action: str, entity_type: str | None = None, entity_id: int | None = None, message: str | None = None) -> AuditLog:
        item = AuditLog(action=action, entity_type=entity_type, entity_id=entity_id, message=message)
        self.session.add(item)
        self.session.flush()
        return item


def dashboard_counts(session: Session) -> dict[str, int]:
    return {
        "companies": session.scalar(select(func.count(Company.id))) or 0,
        "sources": session.scalar(select(func.count(Source.id))) or 0,
        "documents": session.scalar(select(func.count(Document.id))) or 0,
        "events": session.scalar(select(func.count(Event.id)).where(Event.deleted_at.is_(None))) or 0,
        "unread_alerts": session.scalar(
            select(func.count(Alert.id)).where(Alert.status == "unread", Alert.deleted_at.is_(None))
        ) or 0,
    }


def _has_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _company_search_condition(query: str, search_scope: str):
    like = f"%{query}%"
    alias_match = Company.id.in_(
        select(CompanyAlias.company_id).where(CompanyAlias.alias.like(like))
    )
    field_conditions = {
        "name": or_(Company.name.like(like), Company.legal_name.like(like)),
        "legal_name": Company.legal_name.like(like),
        "ticker": Company.ticker.like(like),
        "exchange": Company.exchange.like(like),
        "country": Company.country.like(like),
        "industry": Company.industry.like(like),
        "notes": Company.notes.like(like),
        "alias": alias_match,
    }
    if search_scope in field_conditions:
        return field_conditions[search_scope]
    return or_(
        Company.name.like(like),
        Company.legal_name.like(like),
        Company.ticker.like(like),
        Company.exchange.like(like),
        Company.country.like(like),
        Company.industry.like(like),
        Company.notes.like(like),
        alias_match,
    )
