from __future__ import annotations

from dataclasses import dataclass

from cdm_desktop.event_engine.status_detector import status_strength
from cdm_desktop.event_engine.taxonomy import EVENT_DEFINITIONS


@dataclass(frozen=True)
class ConfidenceResult:
    score: float
    explanation: str


@dataclass(frozen=True)
class MaterialityResult:
    score: float
    explanation: str
    components: dict[str, float]


def source_authority_score(metadata: dict[str, object] | None) -> int:
    metadata = metadata or {}
    source_type = str(metadata.get("source_type") or "").lower()
    url = str(metadata.get("url") or metadata.get("feed_url") or "").lower()
    if source_type == "sec_edgar" or "sec.gov" in url:
        return 95
    if "investor" in url or "/ir" in url or "ir." in url:
        return 85
    if source_type == "rss":
        return 68
    if source_type in {"manual_url", "webpage"}:
        return 62
    return 55


def score_confidence(
    *,
    company_match_confidence: float,
    source_metadata: dict[str, object] | None,
    event_pattern_strength: float,
    event_status: str,
    evidence: str,
    amounts: list[str] | None = None,
    dates: list[str] | None = None,
    counterparties: list[str] | None = None,
) -> ConfidenceResult:
    authority = source_authority_score(source_metadata)
    status = status_strength(event_status)
    evidence_quality = min(95, max(35, len(evidence.strip()) / 2))
    entity_bonus = 0
    if amounts:
        entity_bonus += 6
    if dates:
        entity_bonus += 4
    if counterparties:
        entity_bonus += 4
    score = (
        0.30 * company_match_confidence
        + 0.20 * authority
        + 0.25 * event_pattern_strength
        + 0.15 * status
        + 0.10 * evidence_quality
        + entity_bonus
    )
    if event_status == "rumored":
        score -= 12
    if company_match_confidence < 70:
        score -= 10
    score = round(max(0, min(100, score)), 1)
    explanation = (
        f"公司匹配 {company_match_confidence:.0f}，来源权威性 {authority}，"
        f"事件规则强度 {event_pattern_strength:.0f}，状态明确度 {status}，证据质量 {evidence_quality:.0f}"
    )
    return ConfidenceResult(score=score, explanation=explanation)


def score_materiality(
    *,
    event_type: str,
    source_metadata: dict[str, object] | None,
    event_status: str,
    amounts: list[str] | None = None,
    is_new: bool = True,
) -> MaterialityResult:
    authority = source_authority_score(source_metadata)
    event_weight = EVENT_DEFINITIONS.get(event_type, EVENT_DEFINITIONS["new_business"]).materiality_weight
    financial_scale = _financial_scale(amounts or [])
    governance_impact = _governance_impact(event_type)
    confirmation_level = status_strength(event_status)
    novelty = 80 if is_new else 40
    score = (
        0.25 * authority
        + 0.25 * event_weight
        + 0.15 * financial_scale
        + 0.15 * governance_impact
        + 0.10 * confirmation_level
        + 0.10 * novelty
    )
    score = round(max(0, min(100, score)), 1)
    components = {
        "source_authority": float(authority),
        "event_type_weight": float(event_weight),
        "financial_scale": float(financial_scale),
        "governance_impact": float(governance_impact),
        "confirmation_level": float(confirmation_level),
        "novelty": float(novelty),
    }
    explanation = (
        f"来源 {authority}，事件权重 {event_weight}，财务规模 {financial_scale}，"
        f"治理影响 {governance_impact}，确认程度 {confirmation_level}，新颖性 {novelty}"
    )
    return MaterialityResult(score=score, explanation=explanation, components=components)


def _financial_scale(amounts: list[str]) -> int:
    if not amounts:
        return 40
    joined = " ".join(amounts)
    if any(token in joined for token in ("亿元", "billion", "bn")):
        return 88
    if any(token in joined for token in ("万元", "million", "mn")):
        return 68
    return 58


def _governance_impact(event_type: str) -> int:
    if event_type in {
        "control_change",
        "executive_change",
        "board_change",
        "bankruptcy",
        "debt_default",
        "accounting_restatement",
        "regulatory_investigation",
        "regulatory_penalty",
    }:
        return 88
    if event_type in {"merger_acquisition", "asset_sale", "financing"}:
        return 76
    return 45
