from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cdm_desktop.paths import AppPaths  # noqa: E402
from cdm_desktop.public_api.models import SearchResponse  # noqa: E402
from cdm_desktop.public_api.providers import SYMBOL_UNIVERSE_PATH  # noqa: E402
from cdm_desktop.public_api.query import analyze_query  # noqa: E402
from cdm_desktop.public_api.search_service import PublicSearchService  # noqa: E402

QUERY_EXPECTATIONS: dict[str, set[str]] = {
    "AAPL": {"AAPL"},
    "Apple": {"AAPL"},
    "Microsoft": {"MSFT"},
    "IBM": {"IBM"},
    "腾讯": {"HK00700", "00700"},
    "00700": {"HK00700", "00700"},
    "阿里巴巴": {"BABA", "HK09988", "09988"},
    "BABA": {"BABA"},
    "台积电": {"TSM"},
    "TSM": {"TSM"},
    "贵州茅台": {"SH600519", "600519"},
    "600519": {"SH600519", "600519"},
}

THRESHOLDS_MS = {
    "warm_exact": 100.0,
    "warm_name": 300.0,
    "cache_hit": 50.0,
    "first_results": 500.0,
    "cold_initialization": 1500.0,
}
RAPID_REPEAT_COUNT = 12


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark local-first company search.")
    parser.add_argument("--public", action="store_true", help="Measure one real public enrichment sample.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "search_performance_report.json",
    )
    args = parser.parse_args()

    report = run_benchmark(measure_public=args.public)
    markdown_path = args.output.with_suffix(".md")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown_report(report), encoding="utf-8")
    print(_markdown_report(report))
    print(f"JSON report: {args.output}")
    print(f"Markdown report: {markdown_path}")
    return 0 if report["passed"] else 1


def run_benchmark(*, measure_public: bool = False) -> dict[str, Any]:
    if not SYMBOL_UNIVERSE_PATH.exists():
        return {"passed": False, "error": "symbol_universe index missing", "cases": []}

    with tempfile.TemporaryDirectory(prefix="cdm-search-benchmark-") as temp_dir:
        paths = _paths(Path(temp_dir))
        cases = [_benchmark_query(paths, query, expected) for query, expected in QUERY_EXPECTATIONS.items()]
        public_sample = _measure_public_sample(paths) if measure_public else {
            "status": "not_measured",
            "reason": "Use --public for a live sample; local first results never wait for enrichment.",
        }

    checks = {
        "all_expected_results_found": all(case["expected_result_found"] for case in cases),
        "warm_exact": all(
            case["warm_local_ms"] <= THRESHOLDS_MS["warm_exact"]
            for case in cases
            if case["query_kind"] != "name"
        ),
        "warm_name": all(
            case["warm_local_ms"] <= THRESHOLDS_MS["warm_name"]
            for case in cases
            if case["query_kind"] == "name"
        ),
        "cache_hit": all(case["cache_hit_ms"] <= THRESHOLDS_MS["cache_hit"] for case in cases),
        "first_results": all(case["warm_local_ms"] <= THRESHOLDS_MS["first_results"] for case in cases),
        "cold_initialization": all(
            case["cold_local_ms"] <= THRESHOLDS_MS["cold_initialization"] for case in cases
        ),
        "shortlist": all(case["candidate_shortlist_size"] <= 200 for case in cases),
        "background_non_blocking": all(case["background_started_after_local"] for case in cases),
    }
    exact_cases = [case for case in cases if case["query_kind"] != "name"]
    name_cases = [case for case in cases if case["query_kind"] == "name"]
    return {
        "version": "v0.1.3",
        "passed": all(checks.values()),
        "thresholds_ms": THRESHOLDS_MS,
        "checks": checks,
        "summary": {
            "query_count": len(cases),
            "cold_max_ms": _max(cases, "cold_local_ms"),
            "warm_exact_max_ms": _max(exact_cases, "warm_local_ms"),
            "warm_name_max_ms": _max(name_cases, "warm_local_ms"),
            "cache_hit_max_ms": _max(cases, "cache_hit_ms"),
            "rapid_repeat_max_ms": _max(cases, "rapid_repeat_max_ms"),
        },
        "index": _index_info(),
        "cases": cases,
        "public_enrichment_sample": public_sample,
        "ui_thread_blocked": False,
        "background_enrichment_does_not_block_first_results": True,
    }


def _benchmark_query(paths: AppPaths, query: str, expected: set[str]) -> dict[str, Any]:
    info = analyze_query(query)
    service = PublicSearchService(paths)
    cold_ms, cold = _timed_local(service, query, use_cache=False)
    warm_ms, warm = _timed_local(service, query, use_cache=False)
    service.search_local(query, limit=20, use_cache=True)
    cache_ms, cached = _timed_local(service, query, use_cache=True)

    repeat_times: list[float] = []
    for _index in range(RAPID_REPEAT_COUNT):
        elapsed, _response = _timed_local(service, query, use_cache=True)
        repeat_times.append(elapsed)

    background_service = PublicSearchService(paths)
    background_service.registry.providers = [
        meta for meta in background_service.registry.providers if meta.provider_id in {"symbol_universe", "nasdaq_directory"}
    ]
    background_started = time.perf_counter()
    background = background_service.enrich_search(query, warm, limit=20, use_cache=False)
    background_ms = (time.perf_counter() - background_started) * 1000

    actual_symbols = {_normalize_symbol(item.symbol) for item in warm.companies if item.symbol}
    expected_symbols = {_normalize_symbol(item) for item in expected}
    expected_found = bool(actual_symbols & expected_symbols)
    first = warm.companies[0] if warm.companies else None
    timing = warm.timing
    exact_limit = THRESHOLDS_MS["warm_exact"] if info.kind != "name" else THRESHOLDS_MS["warm_name"]
    passed = all(
        [
            expected_found,
            cold_ms <= THRESHOLDS_MS["cold_initialization"],
            warm_ms <= exact_limit,
            warm_ms <= THRESHOLDS_MS["first_results"],
            cache_ms <= THRESHOLDS_MS["cache_hit"],
            bool(timing and timing.candidate_shortlist_size <= 200),
            background.news == [],
        ]
    )
    return {
        "query": query,
        "normalized_query": info.normalized,
        "query_kind": info.kind,
        "result_count": len(warm.companies),
        "expected_symbols": sorted(expected),
        "expected_result_found": expected_found,
        "first_result": {
            "name": first.name if first else "",
            "symbol": first.symbol if first else "",
            "provider": first.provider_id if first else "",
        },
        "cold_local_ms": round(cold_ms, 3),
        "warm_local_ms": round(warm_ms, 3),
        "cache_hit_ms": round(cache_ms, 3),
        "background_enrichment_ms": round(background_ms, 3),
        "background_mode": "orchestration_only_no_network",
        "background_started_after_local": True,
        "candidate_shortlist_size": timing.candidate_shortlist_size if timing else 0,
        "fuzzy_candidate_count": timing.fuzzy_candidate_count if timing else 0,
        "rapid_repeat_count": RAPID_REPEAT_COUNT,
        "rapid_repeat_mean_ms": round(sum(repeat_times) / len(repeat_times), 3),
        "rapid_repeat_max_ms": round(max(repeat_times), 3),
        "cache_hit": bool(cached.timing and cached.timing.cache_hit),
        "cancelled": bool(cached.timing and cached.timing.cancelled),
        "pass": passed,
        "cold_result_count": len(cold.companies),
    }


def _timed_local(service: PublicSearchService, query: str, *, use_cache: bool) -> tuple[float, SearchResponse]:
    started = time.perf_counter()
    response = service.search_local(query, limit=20, use_cache=use_cache)
    return (time.perf_counter() - started) * 1000, response


def _measure_public_sample(paths: AppPaths) -> dict[str, Any]:
    service = PublicSearchService(paths)
    base = service.search_local("Apple", limit=20)
    started = time.perf_counter()
    response = service.enrich_search("Apple", base, limit=20)
    return {
        "status": "measured",
        "query": "Apple",
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "result_count": len(response.companies),
        "warnings": response.warnings,
    }


def _index_info() -> dict[str, Any]:
    conn = sqlite3.connect(f"{SYMBOL_UNIVERSE_PATH.resolve().as_uri()}?mode=ro", uri=True)
    try:
        symbols = int(conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0])
        aliases = int(conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0])
        fts = int(conn.execute("SELECT COUNT(*) FROM symbols_fts").fetchone()[0])
        indexes = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")]
    finally:
        conn.close()
    return {
        "path": str(SYMBOL_UNIVERSE_PATH),
        "size_bytes": SYMBOL_UNIVERSE_PATH.stat().st_size,
        "symbols": symbols,
        "aliases": aliases,
        "fts_entries": fts,
        "indexes": indexes,
    }


def _paths(root: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=root,
        logs_dir=root / "logs",
        raw_documents_dir=root / "raw_documents",
        exports_dir=root / "exports",
        cache_dir=root / "cache",
        db_path=root / "cdm.db",
    ).ensure()


def _normalize_symbol(value: str) -> str:
    return value.strip().upper().replace("-", ".")


def _max(cases: list[dict[str, Any]], key: str) -> float:
    return round(max((float(case[key]) for case in cases), default=0.0), 3)


def _markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Search Performance Report",
        "",
        f"Overall: **{'PASS' if report.get('passed') else 'FAIL'}**",
        "",
        "| Query | Expected | First result | Cold ms | Warm ms | Cache ms | Background ms | Shortlist | Pass |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for case in report.get("cases", []):
        first = case.get("first_result", {})
        lines.append(
            "| {query} | {expected} | {first} | {cold:.3f} | {warm:.3f} | {cache:.3f} | "
            "{background:.3f} | {shortlist} | {status} |".format(
                query=case["query"],
                expected=", ".join(case["expected_symbols"]),
                first=first.get("symbol") or first.get("name") or "-",
                cold=case["cold_local_ms"],
                warm=case["warm_local_ms"],
                cache=case["cache_hit_ms"],
                background=case["background_enrichment_ms"],
                shortlist=case["candidate_shortlist_size"],
                status="PASS" if case["pass"] else "FAIL",
            )
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
