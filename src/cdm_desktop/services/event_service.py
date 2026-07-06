from __future__ import annotations

from sqlalchemy.orm import Session

from cdm_desktop.db.models import Document
from cdm_desktop.db.repositories import DocumentRepository, EventRepository, dumps_json, loads_json
from cdm_desktop.event_engine.detector import detect_events
from cdm_desktop.services.alert_service import AlertService
from cdm_desktop.services.matching_service import MatchingService


class EventService:
    def __init__(self) -> None:
        self.matching_service = MatchingService()
        self.alert_service = AlertService()

    def process_document(self, session: Session, document_id: int) -> list[int]:
        document = DocumentRepository(session).get(document_id)
        text = document.parsed_text or ""
        matches = self.matching_service.match_document(session, text)
        doc_repo = DocumentRepository(session)
        for match in matches:
            doc_repo.save_match(
                document_id=document.id,
                company_id=match.company_id,
                matched_text=match.matched_text,
                match_type=match.match_type,
                confidence_score=match.confidence_score,
                evidence=match.evidence,
            )

        source_metadata = loads_json(document.metadata_json, {}) or {}
        source_metadata["url"] = document.url
        candidates = detect_events(
            text,
            matches,
            source_metadata=source_metadata,
            document_id=document.id,
        )
        event_repo = EventRepository(session)
        created_ids: list[int] = []
        for candidate in candidates:
            existing = event_repo.find_existing(
                candidate.company_id,
                document.id,
                candidate.event_type,
                candidate.title,
            )
            if existing:
                continue
            event = event_repo.create(
                company_id=candidate.company_id,
                document_id=document.id,
                event_type=candidate.event_type,
                event_status=candidate.event_status,
                title=candidate.title,
                summary=candidate.summary,
                confidence_score=candidate.confidence_score,
                confidence_explanation=candidate.confidence_explanation,
                materiality_score=candidate.materiality_score,
                materiality_explanation=candidate.materiality_explanation,
                score_components_json=dumps_json(candidate.score_components),
                entities_json=dumps_json(candidate.entities),
                amounts_json=dumps_json(candidate.amounts),
            )
            event_repo.add_evidence(
                event_id=event.id,
                document_id=document.id,
                source_url=document.url,
                snippet=candidate.evidence,
                start_offset=candidate.start_offset,
                end_offset=candidate.end_offset,
            )
            self.alert_service.create_for_event(session, event)
            created_ids.append(event.id)
        return created_ids

    def reprocess_document(self, session: Session, document: Document) -> list[int]:
        return self.process_document(session, document.id)
