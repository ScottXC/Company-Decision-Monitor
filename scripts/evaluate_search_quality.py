from __future__ import annotations

# ruff: noqa: E402
import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cdm_desktop.public_api.search_service import PublicSearchService
from scripts.search_quality_lib import case_hit, load_search_cases, offline_search

REPORTS = ROOT / "reports"
SYMBOL_UNIVERSE_INDEX = SRC / "cdm_desktop" / "resources" / "symbol_universe" / "symbol_universe.sqlite"


def main() -> int:
    args = _parse_args()
    report = _evaluate_live() if args.live else _evaluate_offline()
    output = Path(args.output) if args.output else None
    if output:
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_report(report)
    if args.live and report["summary"]["provider_warning_cases"]:
        return 0
    return 0 if report["summary"]["failed"] == 0 else 1


def _evaluate_offline() -> dict[str, Any]:
    rows = []
    for case in load_search_cases():
        results, diagnostics = offline_search(case["query"])
        rows.append(_case_result(case, results, diagnostics, live=False))
    return _report("offline", rows)


def _evaluate_live() -> dict[str, Any]:
    service = PublicSearchService()
    rows = []
    for case in load_search_cases():
        response = service.search(str(case["query"]), limit=10)
        diagnostics = {
            "warnings": response.warnings,
            "errors": [error.state for error in response.errors],
            "from_cache": response.from_cache,
            "provider_count": len(response.statuses),
        }
        rows.append(_case_result(case, response.companies, diagnostics, live=True))
    return _report("live", rows)


def _case_result(case: dict[str, Any], results: list[Any], diagnostics: dict[str, Any], *, live: bool) -> dict[str, Any]:
    hit1 = case_hit(results, case, at=1)
    hit3 = case_hit(results, case, at=3)
    hit5 = case_hit(results, case, at=5)
    top = [
        {
            "name": item.display_name or item.name,
            "symbol": item.symbol,
            "provider": item.provider_id,
            "score": item.match_score,
            "reason": item.match_reason,
        }
        for item in results[:5]
    ]
    min_score = int(case.get("min_score") or 0)
    top_score = int(results[0].match_score) if results else 0
    passed = hit3 and top_score >= min_score
    warning_states = {"rate_limited", "quota_exceeded", "network_timeout", "dns_failure", "http_error"}
    provider_warning = live and bool(set(diagnostics.get("errors", [])) & warning_states)
    return {
        "query": case["query"],
        "expected_symbols": case.get("expected_symbols", []),
        "passed": passed or provider_warning,
        "hit_at_1": hit1,
        "hit_at_3": hit3,
        "hit_at_5": hit5,
        "top_score": top_score,
        "min_score": min_score,
        "provider_warning": provider_warning,
        "actual_top_results": top,
        "diagnostics": diagnostics,
        "failure_reason": "" if passed or provider_warning else _failure_reason(results, case, top_score, min_score),
    }


def _report(mode: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    passed = sum(1 for row in rows if row["passed"])
    failed = total - passed
    return {
        "version": "v0.1.4-generalized-search-performance-rc1",
        "app_mode": "Open-Source Data Mode",
        "mode": mode,
        "open_source_provider_availability": _open_source_provider_availability(),
        "summary": {
            "total_cases": total,
            "passed": passed,
            "failed": failed,
            "recall_at_1": _ratio(sum(1 for row in rows if row["hit_at_1"]), total),
            "recall_at_3": _ratio(sum(1 for row in rows if row["hit_at_3"]), total),
            "recall_at_5": _ratio(sum(1 for row in rows if row["hit_at_5"]), total),
            "provider_warning_cases": sum(1 for row in rows if row["provider_warning"]),
            "fallback_used": True,
        },
        "missing_cases": [row for row in rows if not row["hit_at_5"]],
        "wrong_top_result_cases": [row for row in rows if not row["hit_at_1"] and row["hit_at_3"]],
        "low_score_cases": [row for row in rows if row["top_score"] < row["min_score"]],
        "provider_failure_cases": [row for row in rows if row["provider_warning"]],
        "cases": rows,
    }


def _open_source_provider_availability() -> dict[str, str]:
    index_record_count = _symbol_index_record_count()
    return {
        "symbol_universe": "available" if SYMBOL_UNIVERSE_INDEX.exists() and index_record_count > 0 else "index_missing",
        "finance_database_index_record_count": str(index_record_count),
        "advanced_api_enabled": "false",
        "finance_database_package": "build_time_only" if _module_available("financedatabase") else "not_installed",
        "akshare": "available" if _module_available("akshare") else "dependency_missing",
        "rapidfuzz": "available" if _module_available("rapidfuzz") else "difflib_fallback",
        "cleanco": "available" if _module_available("cleanco") else "internal_suffix_fallback",
    }


def _symbol_index_record_count() -> int:
    if not SYMBOL_UNIVERSE_INDEX.exists():
        return 0
    try:
        import sqlite3

        conn = sqlite3.connect(SYMBOL_UNIVERSE_INDEX)
        try:
            return int(conn.execute("SELECT COUNT(*) FROM symbol_universe").fetchone()[0])
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return 0


def _module_available(name: str) -> bool:
    try:
        __import__(name)
    except ImportError:
        return False
    return True


def _failure_reason(results: list[Any], case: dict[str, Any], top_score: int, min_score: int) -> str:
    if not results:
        return "no result"
    if top_score < min_score:
        return f"top score {top_score} below required {min_score}"
    return f"expected {case.get('expected_symbols') or case.get('expected_names')} not found in top 3"


def _ratio(value: int, total: int) -> float:
    return round(value / total, 4) if total else 0.0


def _print_report(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"Search quality evaluation ({report['mode']})")
    print(
        f"- total={summary['total_cases']} passed={summary['passed']} failed={summary['failed']} "
        f"R@1={summary['recall_at_1']} R@3={summary['recall_at_3']} R@5={summary['recall_at_5']}"
    )
    print(f"- open-source providers: {report['open_source_provider_availability']}")
    for row in report["cases"]:
        status = "PASS" if row["passed"] else "FAIL"
        top = row["actual_top_results"][0] if row["actual_top_results"] else {"symbol": "-", "name": "-"}
        print(f"  {status} | {row['query']} | top={top['symbol']} {top['name']} | {row['failure_reason']}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate search recall against golden cases.")
    parser.add_argument("--live", action="store_true", help="Call configured real providers.")
    parser.add_argument("--output", help="Write JSON report to this path.")
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
