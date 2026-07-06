from __future__ import annotations

from cdm_desktop.event_engine.taxonomy import STATUS_PATTERNS


def detect_status(text: str) -> str:
    haystack = text.lower()
    for status, patterns in STATUS_PATTERNS.items():
        for pattern in patterns:
            if pattern.lower() in haystack:
                return status
    return "unknown"


def status_strength(status: str) -> int:
    return {
        "denied": 75,
        "terminated": 85,
        "completed": 92,
        "shareholder_approved": 88,
        "board_approved": 84,
        "announced": 78,
        "proposed": 68,
        "rumored": 42,
        "unknown": 35,
    }.get(status, 35)
