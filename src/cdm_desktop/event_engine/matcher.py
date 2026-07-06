from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz


@dataclass(frozen=True)
class CompanyAliasProfile:
    alias: str
    alias_type: str = "other"


@dataclass(frozen=True)
class CompanyProfile:
    id: int
    name: str
    ticker: str | None = None
    aliases: tuple[CompanyAliasProfile, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MatchResult:
    company_id: int
    company_name: str
    matched_text: str
    match_type: str
    confidence_score: float
    evidence: str


class CompanyMatcher:
    def match_text(self, text: str, profiles: list[CompanyProfile]) -> list[MatchResult]:
        results: list[MatchResult] = []
        for profile in profiles:
            best = self._match_profile(text, profile)
            if best:
                results.append(best)
        return self._penalize_ambiguous(results)

    def _match_profile(self, text: str, profile: CompanyProfile) -> MatchResult | None:
        candidates: list[MatchResult] = []
        if profile.ticker:
            found = _find_ascii_token(text, profile.ticker)
            if found is not None:
                candidates.append(
                    MatchResult(profile.id, profile.name, profile.ticker, "ticker", 98, _snippet(text, found, len(profile.ticker)))
                )

        fields = [(profile.name, "company_name")]
        fields.extend((alias.alias, alias.alias_type) for alias in profile.aliases)
        for value, alias_type in fields:
            if not value or len(value.strip()) < 2:
                continue
            found = _find_literal(text, value)
            if found is not None:
                score = 95 if alias_type in {"company_name", "legal_name"} else 92
                if alias_type == "ticker":
                    score = 98
                candidates.append(
                    MatchResult(profile.id, profile.name, value, alias_type, score, _snippet(text, found, len(value)))
                )
                continue

            if _is_safe_fuzzy_alias(value):
                fuzzy_score = fuzz.partial_ratio(value.lower(), text.lower())
                if fuzzy_score >= 94:
                    candidates.append(
                        MatchResult(
                            profile.id,
                            profile.name,
                            value,
                            "fuzzy_alias",
                            min(86, fuzzy_score * 0.9),
                            text[:180].strip(),
                        )
                    )

        if not candidates:
            return None
        return max(candidates, key=lambda item: item.confidence_score)

    def _penalize_ambiguous(self, results: list[MatchResult]) -> list[MatchResult]:
        counts: dict[str, int] = {}
        for result in results:
            key = result.matched_text.strip().lower()
            counts[key] = counts.get(key, 0) + 1
        penalized: list[MatchResult] = []
        for result in results:
            key = result.matched_text.strip().lower()
            if counts[key] > 1 and len(key) <= 6:
                penalized.append(
                    MatchResult(
                        result.company_id,
                        result.company_name,
                        result.matched_text,
                        f"ambiguous_{result.match_type}",
                        min(result.confidence_score, 55),
                        result.evidence,
                    )
                )
            else:
                penalized.append(result)
        return penalized


def _find_literal(text: str, needle: str) -> int | None:
    if _is_ascii_word(needle):
        match = re.search(rf"(?<![A-Za-z0-9]){re.escape(needle)}(?![A-Za-z0-9])", text, re.IGNORECASE)
        return match.start() if match else None
    idx = text.lower().find(needle.lower())
    return idx if idx >= 0 else None


def _find_ascii_token(text: str, token: str) -> int | None:
    match = re.search(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])", text, re.IGNORECASE)
    return match.start() if match else None


def _snippet(text: str, start: int, length: int, radius: int = 90) -> str:
    left = max(0, start - radius)
    right = min(len(text), start + length + radius)
    return text[left:right].strip()


def _is_ascii_word(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9 .,&'-]+", value.strip()))


def _is_safe_fuzzy_alias(value: str) -> bool:
    compact = value.strip()
    if len(compact) < 7:
        return False
    return not (compact.upper() == compact and len(compact) <= 6)
