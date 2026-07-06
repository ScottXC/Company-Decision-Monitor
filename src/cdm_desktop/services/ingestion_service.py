from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cdm_desktop.connectors.base import BaseConnector, NormalizedDocument, content_hash
from cdm_desktop.connectors.manual_url import ManualUrlConnector
from cdm_desktop.connectors.rss import RSSConnector
from cdm_desktop.connectors.sec_edgar import SecEdgarConnector
from cdm_desktop.connectors.webpage import WebPageConnector
from cdm_desktop.db import DatabaseManager
from cdm_desktop.db.models import Source
from cdm_desktop.db.repositories import DocumentRepository, SourceRepository, loads_json
from cdm_desktop.paths import AppPaths
from cdm_desktop.services.event_service import EventService
from cdm_desktop.services.parsing_service import ParsingService


@dataclass(frozen=True)
class IngestionResult:
    source_id: int
    run_id: int
    documents_found: int
    documents_created: int
    events_created: int
    status: str
    error_message: str | None = None


class IngestionService:
    def __init__(self, db: DatabaseManager, paths: AppPaths) -> None:
        self.db = db
        self.paths = paths
        self.parser = ParsingService()
        self.event_service = EventService()

    def run_source(self, source_id: int) -> IngestionResult:
        with self.db.session() as session:
            source = SourceRepository(session).get(source_id)
            source_snapshot = _source_snapshot(source)
            run = SourceRepository(session).create_run(source_id)
            run_id = run.id

        try:
            connector = self._connector(source_snapshot["source_type"])
            documents = connector.fetch_documents(source_snapshot["url"], source_snapshot["config"])
            created_count = 0
            events_created = 0
            with self.db.session() as session:
                doc_repo = DocumentRepository(session)
                for normalized in documents:
                    digest = content_hash(normalized.raw_content)
                    if doc_repo.find_duplicate(normalized.canonical_url, digest):
                        continue
                    parsed = self.parser.parse(normalized.raw_content, normalized.content_type, normalized.title)
                    raw_path = self._write_raw_document(source_id, digest, normalized)
                    document = doc_repo.create(
                        source_id=source_id,
                        title=parsed.title or normalized.title or normalized.canonical_url,
                        url=normalized.url,
                        canonical_url=normalized.canonical_url,
                        content_type=normalized.content_type,
                        raw_content_path=str(raw_path),
                        parsed_text=parsed.parsed_text,
                        content_hash=digest,
                        published_at=normalized.published_at,
                        parse_status=parsed.parse_status,
                        parse_error=parsed.parse_error,
                        metadata_json=parsed.metadata_json,
                    )
                    created_count += 1
                    if parsed.parse_status == "success":
                        events_created += len(self.event_service.process_document(session, document.id))
                SourceRepository(session).finish_run(
                    run_id,
                    "success",
                    documents_found=len(documents),
                    documents_created=created_count,
                )
            return IngestionResult(source_id, run_id, len(documents), created_count, events_created, "success")
        except Exception as exc:
            with self.db.session() as session:
                SourceRepository(session).finish_run(run_id, "failed", error_message=str(exc))
            return IngestionResult(source_id, run_id, 0, 0, 0, "failed", str(exc))

    def run_all_enabled_sources(self) -> list[IngestionResult]:
        with self.db.session() as session:
            sources = SourceRepository(session).list(enabled_only=True)
            ids = [source.id for source in sources]
        return [self.run_source(source_id) for source_id in ids]

    def _connector(self, source_type: str) -> BaseConnector:
        if source_type == "manual_url":
            return ManualUrlConnector()
        if source_type == "rss":
            return RSSConnector()
        if source_type == "webpage":
            return WebPageConnector()
        if source_type == "sec_edgar":
            return SecEdgarConnector()
        raise ValueError(f"不支持的数据源类型: {source_type}")

    def _write_raw_document(self, source_id: int, digest: str, doc: NormalizedDocument) -> Path:
        suffix = ".bin"
        content_type = doc.content_type.lower()
        if "html" in content_type:
            suffix = ".html"
        elif "pdf" in content_type:
            suffix = ".pdf"
        elif "text" in content_type:
            suffix = ".txt"
        path = self.paths.raw_documents_dir / f"source-{source_id}-{digest[:16]}{suffix}"
        path.write_bytes(doc.raw_content)
        return path


def _source_snapshot(source: Source) -> dict[str, object]:
    return {
        "id": source.id,
        "name": source.name,
        "source_type": source.source_type,
        "url": source.url,
        "config": loads_json(source.config_json, {}) or {},
    }
