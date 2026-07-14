from __future__ import annotations

import argparse
import json
import random
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cdm_desktop.paths import AppPaths  # noqa: E402
from cdm_desktop.public_api.china_hk_index import CHINA_HK_INDEX_PATH  # noqa: E402
from cdm_desktop.public_api.providers import SYMBOL_UNIVERSE_PATH  # noqa: E402
from cdm_desktop.public_api.search_index_manager import SearchIndexManager  # noqa: E402
from cdm_desktop.public_api.search_service import PublicSearchService  # noqa: E402
from cdm_desktop.public_api.seed_aliases import SEED_ALIASES  # noqa: E402

RANDOM_SEED = 14013
KNOWN_QUERIES = {
    "aapl", "apple", "microsoft", "msft", "ibm", "腾讯", "00700", "阿里巴巴",
    "baba", "台积电", "tsm", "贵州茅台", "600519", "比亚迪", "002594",
    "宁德时代", "300750", "美团", "3690", "小米", "1810",
}


@dataclass(frozen=True)
class Case:
    query: str
    expected_symbol: str
    expected_name: str
    category: str


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark random holdout company searches.")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "unseen_search_benchmark.json")
    parser.add_argument("--single-query", default="", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.single_query:
        return _single_query(args.single_query)
    report = run_benchmark()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = _markdown(report)
    args.output.with_suffix(".md").write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0 if report["passed"] else 1


def run_benchmark() -> dict[str, Any]:
    cases = _build_cases()
    with tempfile.TemporaryDirectory(prefix="cdm-unseen-benchmark-") as temp:
        paths = _paths(Path(temp))
        SearchIndexManager.reset_for_tests()
        service = PublicSearchService(paths)
        service.warmup_local_indexes()
        results = [_measure_case(service, case) for case in cases]
        cold_process = [_measure_cold_process(case) for case in cases[:12]]

    searchable = [item for item in results if item["expected_symbol"]]
    cold = [item["cold_query_ms"] for item in results]
    warm = [item["warm_query_ms"] for item in results]
    cached = [item["cached_query_ms"] for item in results]
    summary = {
        "total_cases": len(results),
        "cold_process_sample_count": len(cold_process),
        "cold_process": _percentiles([item["elapsed_ms"] for item in cold_process]),
        "cold_query": _percentiles(cold),
        "warm_query": _percentiles(warm),
        "cache_hit": _percentiles(cached, include_p99=False),
        "local_first": _percentiles(cold),
        "recall_at_1": _recall(searchable, 1),
        "recall_at_3": _recall(searchable, 3),
        "recall_at_5": _recall(searchable, 5),
        "queries_over_500ms": sum(value > 500 for value in cold),
        "queries_over_1000ms": sum(value > 1000 for value in cold),
        "queries_over_2000ms": sum(value > 2000 for value in cold),
        "shortlist": _percentiles([float(item["shortlist_size"]) for item in results]),
        "max_shortlist": max((item["shortlist_size"] for item in results), default=0),
        "sql_p95_ms": _percentile(sorted(float(item["sql_ms"]) for item in results), 0.95),
        "fuzzy_p95_ms": _percentile(sorted(float(item["fuzzy_ms"]) for item in results), 0.95),
        "seed_alias_used_count": 0,
        "cache_enabled": True,
        "cache_bypassed_for_cold_and_warm": True,
        "network_enrichment": "not included in local timing; scheduled only after local response",
    }
    category_recall = {
        category: {
            "recall_at_1": _recall([item for item in searchable if item["category"] in categories], 1),
            "recall_at_3": _recall([item for item in searchable if item["category"] in categories], 3),
            "recall_at_5": _recall([item for item in searchable if item["category"] in categories], 5),
        }
        for category, categories in {
            "ticker": {"ticker"},
            "english": {"english_name", "multi_word", "prefix"},
            "chinese": {"chinese_name"},
            "typo": {"typo"},
        }.items()
    }
    no_result_times = [item["cold_query_ms"] for item in results if item["category"] == "no_result"]
    summary["no_result_latency"] = _percentiles(no_result_times)
    checks = {
        "cold_ticker_p95": _category_p95(results, "ticker") <= 150,
        "cold_english_p95": _category_p95(results, "english_name") <= 400,
        "cold_chinese_p95": _category_p95(results, "chinese_name") <= 500,
        "warm_p95": summary["warm_query"]["p95"] <= 200,
        "cache_p95": summary["cache_hit"]["p95"] <= 50,
        "local_p95": summary["cold_query"]["p95"] <= 600,
        "recall_at_3": summary["recall_at_3"] >= 0.85,
        "recall_at_5": summary["recall_at_5"] >= 0.92,
        "ticker_recall_at_1": category_recall["ticker"]["recall_at_1"] >= 0.95,
        "no_local_over_2s": max(cold, default=0) <= 2000,
        "shortlist_bounded": summary["max_shortlist"] <= 200,
    }
    return {
        "version": "v0.1.4-generalized-search-performance-rc1",
        "random_seed": RANDOM_SEED,
        "passed": all(checks.values()),
        "checks": checks,
        "summary": summary,
        "category_p95_ms": {
            category: round(_category_p95(results, category), 3)
            for category in sorted({item["category"] for item in results})
        },
        "category_recall": category_recall,
        "failed_cases": [item for item in results if item["expected_symbol"] and not item["found_at_5"]][:50],
        "cases": results,
    }


def _build_cases() -> list[Case]:
    randomizer = random.Random(RANDOM_SEED)
    excluded = set(KNOWN_QUERIES)
    for seed in SEED_ALIASES:
        excluded.update(term.casefold() for term in seed.all_terms())
    global_rows = _sample_rows(SYMBOL_UNIVERSE_PATH, 650, chinese=False)
    global_rows = [row for row in global_rows if row[0].casefold() not in excluded and row[1].casefold() not in excluded]
    randomizer.shuffle(global_rows)
    china_rows = _sample_rows(CHINA_HK_INDEX_PATH, 250, chinese=True) if CHINA_HK_INDEX_PATH.exists() else []
    china_rows = [row for row in china_rows if row[0].casefold() not in excluded and row[1].casefold() not in excluded]
    randomizer.shuffle(china_rows)

    cases: list[Case] = []
    cases.extend(Case(symbol, symbol, name, "ticker") for symbol, name in global_rows[:100])
    names = [(symbol, name) for symbol, name in global_rows if len(name) >= 5]
    cases.extend(Case(name, symbol, name, "english_name") for symbol, name in names[:100])
    cases.extend(Case(name[: max(3, min(len(name) - 1, len(name) // 2))], symbol, name, "prefix") for symbol, name in names[100:150])
    multi = [(symbol, name) for symbol, name in names if len(name.split()) >= 2]
    cases.extend(Case(name, symbol, name, "multi_word") for symbol, name in multi[:50])
    cases.extend(Case(name, symbol, name, "chinese_name") for symbol, name in china_rows[:50])
    typo_source = names[150:200]
    cases.extend(Case(_typo(name), symbol, name, "typo") for symbol, name in typo_source)
    cases.extend(Case(f"noresult-{RANDOM_SEED}-{index:03d}-zxqv", "", "", "no_result") for index in range(50))
    return cases


def _sample_rows(path: Path, count: int, *, chinese: bool) -> list[tuple[str, str]]:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        name_column = "COALESCE(NULLIF(chinese_name,''),name)" if chinese else "name"
        condition = "chinese_name != ''" if chinese else "name != ''"
        return [
            (str(row[0]), str(row[1]))
            for row in connection.execute(
                f"SELECT normalized_symbol,{name_column} FROM symbols WHERE {condition} "
                "ORDER BY ((id * 1103515245 + ?) & 2147483647) LIMIT ?",
                (RANDOM_SEED, count),
            )
        ]
    finally:
        connection.close()


def _measure_case(service: PublicSearchService, case: Case) -> dict[str, Any]:
    service.clear_query_cache()
    cold_ms, cold = _timed(service, case.query, bypass=True)
    warm_ms, warm = _timed(service, case.query, bypass=True)
    service.search_local(case.query, use_cache=True)
    cache_ms, cached = _timed(service, case.query, bypass=False)
    symbols = [_comparable_symbol(item.symbol) for item in cold.companies]
    expected = _comparable_symbol(case.expected_symbol)
    expected_name = _comparable_name(case.expected_name)
    name_matches = [_comparable_name(item.name or item.display_name) == expected_name for item in cold.companies]
    matches = [bool(expected and symbol == expected) or bool(expected_name and name_match) for symbol, name_match in zip(symbols, name_matches, strict=True)]
    timing = cold.timing
    return {
        "query": case.query,
        "expected_symbol": case.expected_symbol,
        "category": case.category,
        "cold_query_ms": round(cold_ms, 3),
        "warm_query_ms": round(warm_ms, 3),
        "cached_query_ms": round(cache_ms, 3),
        "result_count": len(cold.companies),
        "shortlist_size": timing.candidate_shortlist_size if timing else 0,
        "sql_ms": round(timing.local_index_ms, 3) if timing else 0,
        "fuzzy_ms": round(timing.fuzzy_ms, 3) if timing else 0,
        "provider_ms": round(timing.provider_ms, 3) if timing else 0,
        "cache_hit": bool(cached.timing and cached.timing.cache_hit),
        "found_at_1": any(matches[:1]),
        "found_at_3": any(matches[:3]),
        "found_at_5": any(matches[:5]),
        "top_symbols": symbols[:5],
    }


def _timed(service: PublicSearchService, query: str, *, bypass: bool) -> tuple[float, Any]:
    started = time.perf_counter()
    response = service.search_local(
        query,
        use_cache=True,
        bypass_query_cache=bypass,
        diagnostics_mode=True,
    )
    return (time.perf_counter() - started) * 1000, response


def _measure_cold_process(case: Case) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--single-query", case.query],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    elapsed = (time.perf_counter() - started) * 1000
    return {"query": case.query, "elapsed_ms": round(elapsed, 3), "exit_code": completed.returncode}


def _single_query(query: str) -> int:
    with tempfile.TemporaryDirectory(prefix="cdm-cold-process-") as temp:
        SearchIndexManager.reset_for_tests()
        service = PublicSearchService(_paths(Path(temp)))
        response = service.search_local(query, use_cache=False, bypass_query_cache=True)
        print(json.dumps({"count": len(response.companies), "timing": response.timing.to_dict()}))
    return 0


def _paths(root: Path) -> AppPaths:
    return AppPaths(root, root / "logs", root / "raw", root / "exports", root / "cache", root / "cdm.db").ensure()


def _typo(value: str) -> str:
    words = value.split()
    target = words[0]
    if len(target) >= 5:
        index = len(target) - 2
        target = target[:index] + target[index + 1] + target[index] + target[index + 2 :]
    words[0] = target
    return " ".join(words)


def _comparable_symbol(value: str) -> str:
    symbol = value.strip().upper().replace("-", ".")
    if symbol.endswith(".SS"):
        return "SH" + symbol.split(".", 1)[0]
    if symbol.endswith(".SZ"):
        return "SZ" + symbol.split(".", 1)[0]
    if symbol.endswith(".HK"):
        return "HK" + symbol.split(".", 1)[0].zfill(5)
    return symbol


def _comparable_name(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _percentiles(values: list[float], *, include_p99: bool = True) -> dict[str, float]:
    ordered = sorted(values)
    result = {"p50": _percentile(ordered, 0.50), "p95": _percentile(ordered, 0.95)}
    if include_p99:
        result["p99"] = _percentile(ordered, 0.99)
    return result


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, int(round((len(values) - 1) * fraction))))
    return round(values[index], 3)


def _recall(cases: list[dict[str, Any]], rank: int) -> float:
    if not cases:
        return 0.0
    return round(sum(bool(case[f"found_at_{rank}"]) for case in cases) / len(cases), 4)


def _category_p95(cases: list[dict[str, Any]], category: str) -> float:
    values = [case["cold_query_ms"] for case in cases if case["category"] == category]
    return _percentile(sorted(values), 0.95)


def _markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    return "\n".join(
        [
            "# Unseen Search Benchmark",
            "",
            f"Overall: **{'PASS' if report['passed'] else 'FAIL'}**",
            f"Cases: {summary['total_cases']}",
            f"Cold-query p50/p95/p99: {summary['cold_query']}",
            f"Warm-query p50/p95/p99: {summary['warm_query']}",
            f"Cache-hit p50/p95: {summary['cache_hit']}",
            f"Local-first p50/p95/p99: {summary['local_first']}",
            f"Recall@1/@3/@5: {summary['recall_at_1']}/{summary['recall_at_3']}/{summary['recall_at_5']}",
            f"Queries >500ms/>1000ms/>2000ms: {summary['queries_over_500ms']}/{summary['queries_over_1000ms']}/{summary['queries_over_2000ms']}",
            f"Shortlist p50/p95/max: {summary['shortlist']['p50']}/{summary['shortlist']['p95']}/{summary['max_shortlist']}",
            f"SQL/fuzzy p95: {summary['sql_p95_ms']}/{summary['fuzzy_p95_ms']} ms",
            "",
            "## Category cold-query p95",
            *[f"- {key}: {value} ms" for key, value in report["category_p95_ms"].items()],
            "",
            "## Category recall",
            *[f"- {key}: {value}" for key, value in report["category_recall"].items()],
            "",
            "## Checks",
            *[f"- {key}: {'PASS' if value else 'FAIL'}" for key, value in report["checks"].items()],
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
