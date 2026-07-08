from __future__ import annotations

import re
from difflib import SequenceMatcher

COMPANY_SUFFIXES = [
    "incorporated",
    "corporation",
    "corp",
    "limited",
    "ltd",
    "plc",
    "inc",
    "co",
    "company",
    "holdings",
    "holding",
    "股份有限公司",
    "有限公司",
    "集团",
    "公司",
]


def normalize_query(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip().lower())
    cleaned = re.sub(r"[，,。.()\[\]（）【】]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def remove_company_suffix(value: str) -> str:
    normalized = normalize_query(value)
    for suffix in COMPANY_SUFFIXES:
        normalized = re.sub(rf"\b{re.escape(suffix)}\b$", "", normalized).strip()
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip()
    return normalized


def acronym(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    return "".join(word[0].upper() for word in words if word)


def fuzzy_score(query: str, candidate: str) -> int:
    q = remove_company_suffix(query)
    c = remove_company_suffix(candidate)
    if not q or not c:
        return 0
    if q == c:
        return 100
    if q in c or c in q:
        return 86
    if acronym(candidate).lower() == q.lower():
        return 90
    return int(SequenceMatcher(None, q, c).ratio() * 100)
