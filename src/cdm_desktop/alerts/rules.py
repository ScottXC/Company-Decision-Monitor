from __future__ import annotations


def alert_priority(materiality_score: float, confidence_score: float) -> str:
    if materiality_score >= 90 and confidence_score >= 85:
        return "P0"
    if materiality_score >= 75 and confidence_score >= 75:
        return "P1"
    if materiality_score >= 55 and confidence_score >= 60:
        return "P2"
    return "P3"
