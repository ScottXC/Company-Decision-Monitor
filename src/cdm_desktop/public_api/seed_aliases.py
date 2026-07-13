from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeedAlias:
    canonical_name: str
    symbols: tuple[str, ...]
    aliases: tuple[str, ...]
    markets: tuple[str, ...] = ()
    language: str = "mixed"
    confidence: int = 95
    notes: str = "High-confidence public common alias for query expansion only."

    def all_terms(self) -> tuple[str, ...]:
        return (self.canonical_name, *self.symbols, *self.aliases)


# High-confidence query expansion only. These entries are not local company
# records and must never be returned directly as search results.
SEED_ALIASES: tuple[SeedAlias, ...] = (
    SeedAlias("Apple", ("AAPL",), ("Apple Inc.", "苹果"), ("US",)),
    SeedAlias("Microsoft", ("MSFT",), ("Microsoft Corporation", "微软"), ("US",)),
    SeedAlias("Alphabet", ("GOOGL", "GOOG"), ("Google", "谷歌"), ("US",)),
    SeedAlias("Amazon", ("AMZN",), ("Amazon.com", "亚马逊"), ("US",)),
    SeedAlias("Tesla", ("TSLA",), ("Tesla Inc.", "特斯拉"), ("US",)),
    SeedAlias("NVIDIA", ("NVDA",), ("Nvidia", "英伟达"), ("US",)),
    SeedAlias("Meta", ("META",), ("Facebook", "Meta Platforms"), ("US",)),
    SeedAlias("Tencent", ("00700", "HK00700", "TCEHY"), ("Tencent Holdings", "腾讯", "腾讯控股"), ("HK", "US")),
    SeedAlias("Alibaba", ("BABA", "09988", "HK09988"), ("Alibaba Group", "阿里", "阿里巴巴"), ("HK", "US")),
    SeedAlias("TSMC", ("TSM",), ("Taiwan Semiconductor", "Taiwan Semiconductor Manufacturing", "台积电"), ("US", "TW")),
    SeedAlias("BYD", ("BYD", "002594", "SZ002594", "1211", "HK01211", "BYDDY"), ("BYD Company", "比亚迪"), ("CN", "HK", "US")),
    SeedAlias("Kweichow Moutai", ("600519", "SH600519"), ("贵州茅台", "茅台", "Moutai"), ("CN",)),
    SeedAlias("Ping An", ("601318", "SH601318", "02318", "HK02318"), ("Ping An Insurance", "中国平安", "平安"), ("CN", "HK")),
    SeedAlias("HSBC", ("HSBC", "00005", "HK00005"), ("HSBC Holdings", "汇丰", "汇丰控股"), ("HK", "US")),
    SeedAlias("Toyota", ("TM",), ("Toyota Motor", "丰田"), ("US", "JP")),
    SeedAlias("IBM", ("IBM",), ("International Business Machines",), ("US",)),
    SeedAlias("Shell", ("SHEL",), ("Shell plc", "Royal Dutch Shell"), ("US", "UK")),
    SeedAlias("Berkshire Hathaway", ("BRK.B", "BRK-B"), ("Berkshire", "Berkshire Hathaway Class B"), ("US",)),
)


def matching_seed_aliases(query_terms: set[str]) -> list[SeedAlias]:
    normalized_terms = {_normalize(term) for term in query_terms if term}
    matches: list[SeedAlias] = []
    for seed in SEED_ALIASES:
        seed_terms = {_normalize(term) for term in seed.all_terms()}
        if normalized_terms & seed_terms:
            matches.append(seed)
    return matches


def expand_query_aliases(query_terms: set[str], *, max_terms: int = 8) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    for term in sorted(query_terms, key=_term_priority):
        _append(expanded, seen, term)
    for seed in matching_seed_aliases(query_terms):
        priority_terms = (*seed.symbols, seed.canonical_name, *seed.aliases)
        for term in priority_terms:
            _append(expanded, seen, term)
            if len(expanded) >= max_terms:
                return expanded
    return expanded


def seed_aliases_for_query(query_terms: set[str]) -> list[dict[str, object]]:
    return [
        {
            "canonical_name": seed.canonical_name,
            "symbols": list(seed.symbols),
            "markets": list(seed.markets),
            "aliases": list(seed.aliases),
            "language": seed.language,
            "confidence": seed.confidence,
            "notes": seed.notes,
        }
        for seed in matching_seed_aliases(query_terms)
    ]


def seed_alias_exact_match(query_terms: set[str], candidate_terms: set[str]) -> bool:
    normalized_query = {_normalize(term) for term in query_terms if term}
    normalized_candidate = {_normalize(term) for term in candidate_terms if term}
    for seed in matching_seed_aliases(normalized_query):
        seed_terms = {_normalize(term) for term in seed.all_terms()}
        if seed_terms & normalized_candidate:
            return True
    return False


def _append(items: list[str], seen: set[str], value: str) -> None:
    cleaned = value.strip()
    key = _normalize(cleaned)
    if cleaned and key not in seen:
        seen.add(key)
        items.append(cleaned)


def _normalize(value: str) -> str:
    return value.strip().casefold().replace(" ", "")


def _term_priority(value: str) -> tuple[int, int, str]:
    cleaned = value.strip()
    if not cleaned:
        return 9, 0, ""
    if cleaned.isupper() or any(ch.isdigit() for ch in cleaned):
        return 0, len(cleaned), cleaned.casefold()
    return 1, len(cleaned), cleaned.casefold()
