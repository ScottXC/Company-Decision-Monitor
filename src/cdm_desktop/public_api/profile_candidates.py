from __future__ import annotations

import hashlib
import json
from typing import Any

from cdm_desktop.public_api.data_quality import is_meaningful_value
from cdm_desktop.public_api.models import CompanyProfile
from cdm_desktop.public_api.web_evidence_models import ProfileFieldCandidate, WebEvidenceItem

AUTO_ACCEPT_CONFIDENCE = 0.9


def profile_candidates_from_evidence(
    item: WebEvidenceItem,
    profile: CompanyProfile | None = None,
) -> list[ProfileFieldCandidate]:
    current = profile or CompanyProfile()
    candidates: list[ProfileFieldCandidate] = []
    organization = item.structured_data.get("organization")
    if item.is_official_domain and isinstance(organization, dict):
        mappings: tuple[tuple[str, str, float], ...] = (
            ("official_name", "name", 0.96),
            ("legal_name", "legalName", 0.98),
            ("alternate_names", "alternateName", 0.92),
            ("website", "url", 0.99),
            ("logo_url", "logo", 0.94),
            ("address", "address", 0.93),
            ("phone", "telephone", 0.92),
            ("email", "email", 0.92),
            ("founding_date", "foundingDate", 0.91),
        )
        for field_name, source_key, confidence in mappings:
            proposed = organization.get(source_key)
            if not is_meaningful_value(proposed, field_name):
                continue
            profile_field = _profile_field(field_name)
            current_value = getattr(current, profile_field, "")
            status = _candidate_status(
                current_value=current_value,
                proposed_value=proposed,
                confidence=confidence,
                official_json_ld=True,
            )
            candidates.append(
                ProfileFieldCandidate(
                    id=_candidate_id(item.id, field_name, proposed),
                    field_name=field_name,
                    proposed_value=proposed,
                    source_url=item.canonical_url,
                    evidence_id=item.id,
                    confidence=confidence,
                    current_value=current_value,
                    status=status,
                )
            )

    contextual: list[tuple[str, Any, float]] = []
    if item.is_official_domain and item.description:
        contextual.append(("description", item.description, 0.84))
    if item.is_official_domain and item.content_type == "investor_relations":
        contextual.append(("investor_relations_url", item.canonical_url, 0.88))
    if item.is_official_domain and item.content_type in {"press_release", "official_news"}:
        contextual.append(("press_release_url", item.canonical_url, 0.86))
    for field_name, proposed, confidence in contextual:
        current_value = getattr(current, field_name, "")
        candidates.append(
            ProfileFieldCandidate(
                id=_candidate_id(item.id, field_name, proposed),
                field_name=field_name,
                proposed_value=proposed,
                source_url=item.canonical_url,
                evidence_id=item.id,
                confidence=confidence,
                current_value=current_value,
                status="pending",
            )
        )
    return _dedupe_candidates(candidates)


def apply_auto_accepted_candidates(
    profile: CompanyProfile,
    candidates: list[ProfileFieldCandidate],
) -> CompanyProfile:
    for candidate in candidates:
        profile_field = _profile_field(candidate.field_name)
        current = getattr(profile, profile_field, None)
        record = {
            "value": candidate.proposed_value,
            "provider": "official_website_evidence",
            "source_url": candidate.source_url,
            "evidence_id": candidate.evidence_id,
            "confidence": candidate.confidence,
            "status": candidate.status,
        }
        records = profile.field_candidates.setdefault(profile_field, [])
        if not any(
            existing.get("evidence_id") == candidate.evidence_id
            and existing.get("value") == candidate.proposed_value
            and existing.get("status") == candidate.status
            for existing in records
        ):
            records.append(record)
        if candidate.status not in {"auto_accepted", "accepted"}:
            continue
        if candidate.status == "auto_accepted" and is_meaningful_value(current, profile_field):
            continue
        value = candidate.proposed_value
        if profile_field == "aliases":
            value = value if isinstance(value, list) else [str(value)]
        setattr(profile, profile_field, value)
        profile.field_sources[profile_field] = "official_website_evidence"
    return profile


def _candidate_status(
    *,
    current_value: Any,
    proposed_value: Any,
    confidence: float,
    official_json_ld: bool,
) -> str:
    if (
        official_json_ld
        and confidence >= AUTO_ACCEPT_CONFIDENCE
        and not is_meaningful_value(current_value)
        and is_meaningful_value(proposed_value)
    ):
        return "auto_accepted"
    return "pending"


def _profile_field(field_name: str) -> str:
    return {
        "alternate_names": "aliases",
    }.get(field_name, field_name)


def _dedupe_candidates(candidates: list[ProfileFieldCandidate]) -> list[ProfileFieldCandidate]:
    result: list[ProfileFieldCandidate] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        key = (candidate.field_name, str(candidate.proposed_value))
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def _candidate_id(evidence_id: str, field_name: str, value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(f"{evidence_id}\n{field_name}\n{serialized}".encode()).hexdigest()
