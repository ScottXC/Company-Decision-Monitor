from __future__ import annotations

import re
from dataclasses import dataclass

from cdm_desktop.event_engine.matcher import MatchResult
from cdm_desktop.event_engine.scoring import score_confidence, score_materiality
from cdm_desktop.event_engine.status_detector import detect_status
from cdm_desktop.event_engine.taxonomy import EVENT_DEFINITIONS


@dataclass(frozen=True)
class CandidateEvent:
    company_id: int
    company_name: str
    document_id: int | None
    event_type: str
    event_status: str
    title: str
    summary: str
    evidence: str
    start_offset: int
    end_offset: int
    confidence_score: float
    confidence_explanation: str
    materiality_score: float
    materiality_explanation: str
    score_components: dict[str, float]
    entities: dict[str, object]
    amounts: list[str]


def detect_events(
    text: str,
    company_matches: list[MatchResult],
    *,
    source_metadata: dict[str, object] | None = None,
    document_id: int | None = None,
) -> list[CandidateEvent]:
    if not text.strip() or not company_matches:
        return []

    source_metadata = source_metadata or {}
    events: list[CandidateEvent] = []
    for match in company_matches:
        if match.confidence_score < 50:
            continue
        for event_type, definition in EVENT_DEFINITIONS.items():
            found = _find_event_keyword(text, definition.keywords_zh + definition.keywords_en)
            if not found:
                continue
            keyword, start = found
            snippet = _snippet(text, start, len(keyword))
            if not snippet:
                continue
            status = detect_status(snippet)
            amounts = _extract_amounts(snippet)
            dates = _extract_dates(snippet)
            counterparties = _extract_counterparties(snippet)
            pattern_strength = _pattern_strength(keyword, snippet)
            confidence = score_confidence(
                company_match_confidence=match.confidence_score,
                source_metadata=source_metadata,
                event_pattern_strength=pattern_strength,
                event_status=status,
                evidence=snippet,
                amounts=amounts,
                dates=dates,
                counterparties=counterparties,
            )
            materiality = score_materiality(
                event_type=event_type,
                source_metadata=source_metadata,
                event_status=status,
                amounts=amounts,
                is_new=True,
            )
            display = definition.display_name_zh
            events.append(
                CandidateEvent(
                    company_id=match.company_id,
                    company_name=match.company_name,
                    document_id=document_id,
                    event_type=event_type,
                    event_status=status,
                    title=f"{match.company_name} - {display}",
                    summary=_summary(snippet),
                    evidence=snippet,
                    start_offset=max(0, start - 180),
                    end_offset=min(len(text), start + len(keyword) + 180),
                    confidence_score=confidence.score,
                    confidence_explanation=confidence.explanation,
                    materiality_score=materiality.score,
                    materiality_explanation=materiality.explanation,
                    score_components=materiality.components,
                    entities={"keyword": keyword, "counterparties": counterparties},
                    amounts=amounts,
                )
            )
    return _dedupe_candidates(events)


def _find_event_keyword(text: str, keywords: tuple[str, ...]) -> tuple[str, int] | None:
    lower_text = text.lower()
    for keyword in keywords:
        idx = lower_text.find(keyword.lower())
        if idx >= 0:
            return keyword, idx
    return None


def _snippet(text: str, start: int, length: int, radius: int = 180) -> str:
    left = max(0, start - radius)
    right = min(len(text), start + length + radius)
    return text[left:right].strip()


def _summary(snippet: str) -> str:
    return re.sub(r"\s+", " ", snippet).strip()[:240]


def _pattern_strength(keyword: str, snippet: str) -> int:
    explicit_terms = ("重大", "审议通过", "公告", "approved", "announced", "material", "definitive")
    base = 78 if len(keyword) >= 4 else 66
    if any(term in snippet.lower() for term in explicit_terms):
        base += 10
    return min(95, base)


def _extract_amounts(text: str) -> list[str]:
    patterns = [
        r"人民币\s?\d+(?:\.\d+)?\s?[万亿]?元",
        r"\d+(?:\.\d+)?\s?[万亿]元",
        r"\$?\d+(?:\.\d+)?\s?(?:billion|million|bn|mn)",
    ]
    amounts: list[str] = []
    for pattern in patterns:
        amounts.extend(re.findall(pattern, text, flags=re.IGNORECASE))
    return amounts[:5]


def _extract_dates(text: str) -> list[str]:
    patterns = [
        r"\d{4}年\d{1,2}月\d{1,2}日",
        r"\d{4}-\d{1,2}-\d{1,2}",
        r"\b\d{1,2}/\d{1,2}/\d{4}\b",
    ]
    dates: list[str] = []
    for pattern in patterns:
        dates.extend(re.findall(pattern, text))
    return dates[:5]


def _extract_counterparties(text: str) -> list[str]:
    items = re.findall(r"(?:收购|acquire|with)\s+([A-Z][A-Za-z0-9 &.,-]{2,60})", text)
    return [item.strip(" 。,.;") for item in items[:5]]


def _dedupe_candidates(events: list[CandidateEvent]) -> list[CandidateEvent]:
    seen: set[tuple[int, str, str]] = set()
    unique: list[CandidateEvent] = []
    for event in sorted(events, key=lambda item: item.confidence_score, reverse=True):
        key = (event.company_id, event.event_type, event.evidence[:80])
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return unique
