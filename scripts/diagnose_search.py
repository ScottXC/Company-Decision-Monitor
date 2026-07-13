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

from cdm_desktop.public_api.news_service import build_news_query_terms
from cdm_desktop.public_api.query import analyze_query
from cdm_desktop.public_api.search_service import PublicSearchService
from scripts.search_quality_lib import offline_search

REPORTS = ROOT / "reports"


def main() -> int:
    args = _parse_args()
    report = _live_report(args.query) if args.live else _offline_report(args.query)
    if args.json_path:
        output = Path(args.json_path)
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_report(report)
    return 0


def _offline_report(query: str) -> dict[str, Any]:
    results, diagnostics = offline_search(query)
    top = [_company_row(item) for item in results[:10]]
    grouped = diagnostics.get("grouped_counts", {})
    best = results[0] if results else None
    return {
        "mode": "offline",
        **diagnostics,
        "provider_call_plan": ["offline_search_quality_fixture"],
        "provider_status": [{"provider": "offline_fixture", "state": "enabled", "result_count": len(results)}],
        "provider_errors": [],
        "top_results": top,
        "dropped_result_reasons": [
            {"name": item.name, "score": item.match_score, "reason": "below possible-match threshold"}
            for item in results
            if item.match_score < 70
        ],
        "final_grouped_results": grouped,
        "news_query_variants": build_news_query_terms(best) if best else [],
        "news_provider_result_count": 0,
    }


def _live_report(query: str) -> dict[str, Any]:
    service = PublicSearchService()
    info = analyze_query(query)
    response = service.search(query, limit=10)
    return {
        "mode": "live",
        "raw_query": query,
        "normalized_query": info.normalized,
        "detected_query_type": info.kind,
        "market_hint": info.market_hint,
        "symbol": info.symbol,
        "query_variants": list(info.variants),
        "provider_call_plan": service.selected_provider_ids(),
        "provider_status": [
            {
                "provider": status.provider_id,
                "state": status.state,
                "message": _redact(status.message),
            }
            for status in response.statuses
        ],
        "provider_errors": [
            {"provider": error.provider_id, "state": error.state, "message": _redact(error.message)}
            for error in response.errors
        ],
        "dedup_before_count": "live-provider-owned",
        "dedup_after_count": len(response.companies),
        "top_results": [_company_row(item) for item in response.companies[:10]],
        "dropped_result_reasons": [],
        "final_grouped_results": {key: len(value) for key, value in response.grouped_results.items()},
        "news_query_variants": build_news_query_terms(response.companies[0]) if response.companies else [],
        "news_provider_result_count": len(response.news),
        "from_cache": response.from_cache,
        "warnings": [_redact(item) for item in response.warnings],
    }


def _company_row(item) -> dict[str, Any]:  # noqa: ANN001
    return {
        "name": item.display_name or item.name,
        "symbol": item.symbol,
        "exchange": item.exchange,
        "market": item.market,
        "provider": item.provider_id,
        "score": item.match_score,
        "reason": item.match_reason,
        "from_cache": item.from_cache,
        "provider_sources": item.raw.get("provider_sources", [item.provider_id]),
    }


def _print_report(report: dict[str, Any]) -> None:
    print(f"Search diagnosis ({report['mode']})")
    print(f"- raw query: {report['raw_query']}")
    print(f"- normalized: {report['normalized_query']}")
    print(f"- detected type: {report['detected_query_type']}")
    print(f"- variants: {', '.join(report.get('query_variants', [])[:12])}")
    print("- top results:")
    for item in report.get("top_results", [])[:10]:
        print(f"  {item['score']:>3} | {item['symbol'] or '-':<10} | {item['name']} | {item['provider']} | {item['reason']}")
    if not report.get("top_results"):
        print("  no offline/live result")


def _redact(value: str) -> str:
    return (
        str(value)
        .replace("apikey=", "apikey=***")
        .replace("api_token=", "api_token=***")
        .replace("token=", "token=***")
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose Company Decision Monitor search recall.")
    parser.add_argument("query", help="Company name, symbol, alias, LEI, or registry number.")
    parser.add_argument("--live", action="store_true", help="Call configured real providers.")
    parser.add_argument("--json", dest="json_path", help="Write JSON report to this path.")
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
