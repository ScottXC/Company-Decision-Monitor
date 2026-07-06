from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(255))
    ticker: Mapped[str | None] = mapped_column(String(64), index=True)
    exchange: Mapped[str | None] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(128))
    industry: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    source_provider: Mapped[str | None] = mapped_column(String(128))
    source_url: Mapped[str | None] = mapped_column(Text)
    source_metadata_json: Mapped[str | None] = mapped_column(Text)

    aliases: Mapped[list[CompanyAlias]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    watchlist_items: Mapped[list[WatchlistItem]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )


class CompanyAlias(Base):
    __tablename__ = "company_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    alias_type: Mapped[str] = mapped_column(String(64), nullable=False, default="other")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    company: Mapped[Company] = relationship(back_populates="aliases")


class CompanyUniverse(Base, TimestampMixin):
    __tablename__ = "company_universe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(255))
    ticker: Mapped[str | None] = mapped_column(String(64), index=True)
    exchange: Mapped[str | None] = mapped_column(String(64), index=True)
    country: Mapped[str | None] = mapped_column(String(128), index=True)
    industry: Mapped[str | None] = mapped_column(String(255))
    aliases_json: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(64), default="online", nullable=False, index=True)
    source_provider: Mapped[str | None] = mapped_column(String(128), index=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    raw_payload_json: Mapped[str | None] = mapped_column(Text)
    popularity_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime)

    company: Mapped[Company] = relationship(back_populates="watchlist_items")

    __table_args__ = (
        Index("ix_watchlist_items_company_active", "company_id", "is_active"),
    )


class Source(Base, TimestampMixin):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    config_json: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)

    runs: Mapped[list[SourceRun]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )


class SourceRun(Base):
    __tablename__ = "source_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    documents_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    documents_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    source: Mapped[Source] = relationship(back_populates="runs")


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128))
    raw_content_path: Mapped[str | None] = mapped_column(Text)
    parsed_text: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    parse_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    parse_error: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_documents_canonical_url", "canonical_url"),
        Index("ix_documents_content_hash", "content_hash"),
        Index("ix_documents_created_at", "created_at"),
    )


class DocumentCompanyMatch(Base):
    __tablename__ = "document_company_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    matched_text: Mapped[str] = mapped_column(String(255), nullable=False)
    match_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (Index("ix_document_company_matches_created_at", "created_at"),)


class Event(Base, TimestampMixin):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    event_status: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown", index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    event_date: Mapped[datetime | None] = mapped_column(DateTime)
    announcement_time: Mapped[datetime | None] = mapped_column(DateTime)
    effective_date: Mapped[datetime | None] = mapped_column(DateTime)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_explanation: Mapped[str | None] = mapped_column(Text)
    materiality_score: Mapped[float] = mapped_column(Float, nullable=False)
    materiality_explanation: Mapped[str | None] = mapped_column(Text)
    score_components_json: Mapped[str | None] = mapped_column(Text)
    entities_json: Mapped[str | None] = mapped_column(Text)
    amounts_json: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)

    __table_args__ = (
        Index("ix_events_created_at", "created_at"),
        Index("ix_events_company_type", "company_id", "event_type"),
    )


class EventEvidence(Base):
    __tablename__ = "event_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unread", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)
    ignored_at: Mapped[datetime | None] = mapped_column(DateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)


class RecycleBinItem(Base):
    __tablename__ = "recycle_bin_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False, index=True)
    deleted_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False, index=True)
    restored_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        Index("ix_recycle_bin_type_entity", "item_type", "entity_id"),
        Index("ix_recycle_bin_status_deleted", "status", "deleted_at"),
    )


class OnlineProviderCache(Base):
    __tablename__ = "online_provider_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    cache_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    payload_path_or_json: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="success", index=True)

    __table_args__ = (
        Index("ix_online_provider_cache_provider_key", "provider_id", "cache_key"),
    )


class OnlineSearchResult(Base):
    __tablename__ = "online_search_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    results_json: Mapped[str] = mapped_column(Text, nullable=False)
    provider_status_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)

    __table_args__ = (
        Index("ix_online_search_results_query_scope", "query", "scope"),
    )


class RecentSearch(Base):
    __tablename__ = "recent_searches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False, index=True)


class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(128))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False, index=True)
