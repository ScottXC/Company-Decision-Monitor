from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from cdm_desktop.public_api.seed_aliases import expand_query_aliases

try:
    from rapidfuzz import fuzz as rapidfuzz_fuzz
except ImportError:  # pragma: no cover - tested through fallback monkeypatch
    rapidfuzz_fuzz = None

try:
    from cleanco import basename as cleanco_basename
except ImportError:  # pragma: no cover - optional dependency
    cleanco_basename = None

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
    "llc",
    "llp",
    "holdings",
    "holding",
    "group",
    "class a",
    "class b",
    "common stock",
    "ordinary shares",
    "ads",
    "adr",
    "sa",
    "sas",
    "gmbh",
    "ag",
    "bv",
    "nv",
    "kk",
    "kabushiki kaisha",
    "pty ltd",
    "ltda",
    "spa",
    "股份有限公司",
    "有限责任公司",
    "有限公司",
    "集团",
    "控股",
    "股份",
    "a股",
    "h股",
    "普通股",
    "公司",
]

QueryKind = Literal["empty", "lei", "hk_symbol", "cn_symbol", "us_symbol", "symbol", "name"]

PREFIX_PATTERN = re.compile(r"^(NASDAQ|NYSE|AMEX|HK|SH|SZ|BJ)[:.\-\s]*([A-Z0-9.\-]+)$", re.IGNORECASE)
LEI_PATTERN = re.compile(r"^[A-Z0-9]{20}$")
HK_SYMBOL_PATTERN = re.compile(r"^(?:HK)?0*\d{1,5}$", re.IGNORECASE)
CN_SYMBOL_PATTERN = re.compile(r"^(?:(SH|SZ|BJ))?(\d{6})$", re.IGNORECASE)
US_SYMBOL_PATTERN = re.compile(r"^[A-Z]{1,6}(?:[.\-][A-Z])?$", re.IGNORECASE)


@dataclass(frozen=True)
class QueryInfo:
    original: str
    normalized: str
    normalized_no_suffix: str
    upper: str
    kind: QueryKind
    market_hint: str = ""
    symbol: str = ""
    variants: tuple[str, ...] = ()


def normalize_query(value: str) -> str:
    cleaned = unicodedata.normalize("NFKC", value or "")
    cleaned = cleaned.replace("（", "(").replace("）", ")").replace("【", "[").replace("】", "]")
    cleaned = cleaned.replace("，", ",").replace("。", ".")
    cleaned = re.sub(r"\s+", " ", cleaned.strip().casefold())
    cleaned = re.sub(r"[,。\.\[\]{}()]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def remove_company_suffix(value: str) -> str:
    normalized = normalize_query(value)
    if cleanco_basename and _mostly_latin(normalized):
        try:
            normalized = normalize_query(cleanco_basename(value))
        except Exception:  # noqa: BLE001
            normalized = normalize_query(value)
    for suffix in sorted(COMPANY_SUFFIXES, key=len, reverse=True):
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
    if rapidfuzz_fuzz is not None:
        if _is_short_cjk(q) or _is_short_cjk(c):
            return int(rapidfuzz_fuzz.ratio(q, c))
        scores = [
            rapidfuzz_fuzz.ratio(q, c),
            rapidfuzz_fuzz.partial_ratio(q, c),
            rapidfuzz_fuzz.token_sort_ratio(q, c),
            rapidfuzz_fuzz.token_set_ratio(q, c),
            rapidfuzz_fuzz.WRatio(q, c),
        ]
        return int(max(scores))
    return int(SequenceMatcher(None, q, c).ratio() * 100)


def shortlist_fuzzy_score(query: str, candidate: str) -> int:
    """Fast reranking score for candidates already selected by SQLite."""
    q = normalize_query(query)
    c = normalize_query(candidate)
    if not q or not c:
        return 0
    if q == c:
        return 100
    if c.startswith(q) or q.startswith(c):
        return 86
    if acronym(candidate).casefold() == q.casefold():
        return 90
    if rapidfuzz_fuzz is not None:
        if _is_short_cjk(q) or _is_short_cjk(c):
            return int(rapidfuzz_fuzz.ratio(q, c))
        return int(rapidfuzz_fuzz.WRatio(q, c))
    return int(SequenceMatcher(None, q, c).ratio() * 100)


def analyze_query(value: str) -> QueryInfo:
    original = value or ""
    normalized = normalize_query(original)
    no_suffix = remove_company_suffix(original)
    upper = _upper_compact(original)
    if not normalized:
        return QueryInfo(original=original, normalized="", normalized_no_suffix="", upper="", kind="empty")

    symbol = ""
    market_hint = ""
    kind: QueryKind = "name"

    prefixed = PREFIX_PATTERN.match(upper)
    if prefixed:
        prefix, body = prefixed.groups()
        market_hint = prefix.upper()
        symbol = _normalize_prefixed_symbol(prefix.upper(), body)
        kind = _kind_for_symbol(symbol, market_hint)
    elif LEI_PATTERN.match(upper):
        symbol = upper
        kind = "lei"
    elif HK_SYMBOL_PATTERN.match(upper) and not CN_SYMBOL_PATTERN.match(upper):
        symbol = normalize_hk_symbol(upper)
        market_hint = "HK"
        kind = "hk_symbol"
    elif CN_SYMBOL_PATTERN.match(upper):
        symbol = normalize_cn_symbol(upper)
        market_hint = symbol[:2] if symbol[:2] in {"SH", "SZ", "BJ"} else _cn_prefix(symbol)
        kind = "cn_symbol"
    elif US_SYMBOL_PATTERN.match(upper):
        symbol = upper.replace("-", ".")
        market_hint = "US"
        kind = "us_symbol"

    base_terms = {original, normalized, no_suffix, upper}
    if symbol:
        base_terms.add(symbol)
        if symbol.startswith("HK"):
            base_terms.add(symbol[2:])
            base_terms.add(symbol[2:].lstrip("0") or symbol[2:])
        if symbol.startswith(("SH", "SZ", "BJ")):
            base_terms.add(symbol[2:])
        if "." in symbol:
            base_terms.add(symbol.replace(".", "-"))
        if "-" in symbol:
            base_terms.add(symbol.replace("-", "."))
    if upper.isdigit():
        for candidate in numeric_symbol_candidates(upper):
            base_terms.add(candidate)
            if candidate.startswith(("HK", "SH", "SZ", "BJ")):
                base_terms.add(candidate[2:])
    variants = tuple(expand_query_aliases({term for term in base_terms if term}, max_terms=16))
    return QueryInfo(
        original=original,
        normalized=normalized,
        normalized_no_suffix=no_suffix,
        upper=upper,
        kind=kind,
        market_hint=market_hint,
        symbol=symbol,
        variants=variants,
    )


def query_variants(value: str, *, max_terms: int = 8) -> list[str]:
    info = analyze_query(value)
    return list(info.variants[:max_terms]) if info.variants else [value.strip()]


def normalize_hk_symbol(value: str) -> str:
    cleaned = _upper_compact(value)
    if cleaned.startswith("HK"):
        cleaned = cleaned[2:]
    digits = re.sub(r"\D", "", cleaned)
    return f"HK{digits.zfill(5)}" if digits else ""


def normalize_cn_symbol(value: str) -> str:
    cleaned = _upper_compact(value)
    match = CN_SYMBOL_PATTERN.match(cleaned)
    if not match:
        return cleaned
    prefix, digits = match.groups()
    prefix = (prefix or _cn_prefix(digits)).upper()
    return f"{prefix}{digits}"


def numeric_symbol_candidates(value: str, *, prefer_market: str = "") -> list[str]:
    digits = re.sub(r"\D", "", value or "")
    if not digits:
        return []
    candidates: list[str] = []
    if len(digits) == 6:
        candidates.append(normalize_cn_symbol(digits))
    if len(digits) <= 5:
        candidates.append(normalize_hk_symbol(digits))
    if prefer_market.upper() == "HK" and normalize_hk_symbol(digits) not in candidates:
        candidates.insert(0, normalize_hk_symbol(digits))
    if prefer_market.upper() in {"CN", "SH", "SZ"} and len(digits) == 6:
        cn = normalize_cn_symbol(digits)
        if cn in candidates:
            candidates.remove(cn)
        candidates.insert(0, cn)
    return [candidate for index, candidate in enumerate(candidates) if candidate and candidate not in candidates[:index]]


def _normalize_prefixed_symbol(prefix: str, body: str) -> str:
    if prefix == "HK":
        return normalize_hk_symbol(f"HK{body}")
    if prefix in {"SH", "SZ", "BJ"}:
        return normalize_cn_symbol(f"{prefix}{body}")
    return body.replace("-", ".").upper()


def _kind_for_symbol(symbol: str, prefix: str) -> QueryKind:
    if prefix == "HK" or symbol.startswith("HK"):
        return "hk_symbol"
    if prefix in {"SH", "SZ", "BJ"} or symbol.startswith(("SH", "SZ", "BJ")):
        return "cn_symbol"
    if LEI_PATTERN.match(symbol):
        return "lei"
    return "us_symbol"


def _cn_prefix(digits_or_symbol: str) -> str:
    digits = re.sub(r"\D", "", digits_or_symbol)
    if digits.startswith("6"):
        return "SH"
    if digits.startswith(("0", "2", "3")):
        return "SZ"
    if digits.startswith(("4", "8", "9")):
        return "BJ"
    return "CN"


def _upper_compact(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value or "").strip().upper())


def _mostly_latin(value: str) -> bool:
    letters = [ch for ch in value if ch.isalpha()]
    if not letters:
        return False
    latin = [ch for ch in letters if "a" <= ch.casefold() <= "z"]
    return len(latin) / len(letters) >= 0.6


def _is_short_cjk(value: str) -> bool:
    return len(value) <= 4 and any("\u4e00" <= ch <= "\u9fff" for ch in value)
