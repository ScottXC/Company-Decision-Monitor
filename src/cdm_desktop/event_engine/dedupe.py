from __future__ import annotations

import hashlib
import re


def event_fingerprint(company_id: int, event_type: str, title: str, evidence: str) -> str:
    normalized = re.sub(r"\s+", " ", f"{company_id}|{event_type}|{title}|{evidence[:160]}").lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def is_similar_event(existing_fingerprints: set[str], fingerprint: str) -> bool:
    return fingerprint in existing_fingerprints
