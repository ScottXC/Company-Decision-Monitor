from __future__ import annotations

# ruff: noqa: E402
import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for entry in (ROOT, SRC):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from cdm_desktop.public_api.data_quality import profile_coverage
from cdm_desktop.public_api.profile_service import CompanyProfileService
from cdm_desktop.public_api.search_service import PublicSearchService

FIXTURE = ROOT / "tests" / "fixtures" / "profile_quality_cases.json"
RC_QUERY_MATRIX = {
    "Apple": ["Apple", "AAPL"],
    "Microsoft": ["Microsoft", "MSFT"],
    "IBM": ["IBM"],
    "Tencent": ["腾讯", "腾讯控股", "00700"],
    "Alibaba": ["阿里巴巴", "09988"],
    "Kweichow Moutai": ["贵州茅台", "600519"],
    "BYD": ["比亚迪", "002594"],
    "Ping An": ["中国平安", "601318"],
    "Toyota": ["Toyota", "TM"],
    "TSMC": ["TSMC", "TSM"],
    "HSBC": ["HSBC"],
    "Shell": ["Shell"],
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate company-profile field coverage.")
    parser.add_argument("--live", action="store_true", help="Enable public no-key enrichment.")
    parser.add_argument("--output", default="reports/profile_coverage_report.json")
    args = parser.parse_args()

    cases = _expanded_cases(json.loads(FIXTURE.read_text(encoding="utf-8")))
    search_service = PublicSearchService()
    profile_service = CompanyProfileService()
    rows = []
    for case in cases:
        response = search_service.search_local(case["query"], limit=5)
        selected = _select(response.companies, case["symbols"])
        if selected is None:
            rows.append({"query": case["query"], "passed": False, "error": "No expected local result."})
            continue
        initial = profile_service.get_immediate_profile(selected)
        statuses = []
        profile = initial
        if args.live:
            profile, statuses = profile_service.get_profile(selected)
            profile = profile or initial
        coverage = profile_coverage(profile)
        threshold = case["min_total_coverage"] if args.live else min(case["min_total_coverage"], 35)
        passed = coverage.identity_coverage >= case["min_identity_coverage"] and coverage.coverage_percent >= threshold
        rows.append(
            {
                "query": case["query"],
                "selected": {"name": selected.name, "symbol": selected.symbol},
                "expected_symbol_found": selected.symbol.upper().replace("-", ".")
                in {item.upper().replace("-", ".") for item in case["symbols"]},
                "initial_field_count": profile_coverage(initial).populated_fields,
                "enriched_field_count": coverage.populated_fields,
                **coverage.to_dict(),
                "missing_key_fields": [
                    field for field in case["expected_identity_fields"] if field in coverage.unresolved_fields
                ],
                "provider_errors": [
                    {"provider": status.provider_id, "state": status.state, "message": status.message}
                    for status in statuses
                    if status.state not in {"enabled", "not_configured"}
                ],
                "profile": {
                    "display_name": profile.display_name,
                    "symbol": profile.symbol,
                    "exchange": profile.exchange,
                    "market": profile.market,
                    "country": profile.country,
                    "sector": profile.sector,
                    "industry": profile.industry,
                    "description": profile.description,
                    "website": profile.website,
                    "legal_name": profile.legal_name,
                    "lei": profile.lei,
                    "registration_status": profile.registration_status,
                    "provider_sources": profile.provider_sources,
                    "field_sources": profile.field_sources,
                    "from_cache": profile.from_cache,
                },
                "passed": passed,
            }
        )
    report = {
        "mode": "public_no_key" if args.live else "local_index",
        "total": len(rows),
        "passed": sum(bool(row.get("passed")) for row in rows),
        "failed": sum(not bool(row.get("passed")) for row in rows),
        "cases": rows,
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = _markdown(report)
    output.with_suffix(".md").write_text(markdown, encoding="utf-8")
    print(markdown)
    return 0 if report["failed"] == 0 else 1


def _expanded_cases(base_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_query = {case["query"]: case for case in base_cases}
    expanded: list[dict[str, Any]] = []
    for canonical, queries in RC_QUERY_MATRIX.items():
        base = by_query[canonical]
        for query in queries:
            expanded.append({**base, "query": query, "canonical_query": canonical})
    return expanded


def _select(companies: list[Any], symbols: list[str]):
    expected = {item.upper().replace("-", ".") for item in symbols}
    return next(
        (item for item in companies if item.symbol.upper().replace("-", ".") in expected),
        companies[0] if companies else None,
    )


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Profile coverage report",
        "",
        f"Mode: {report['mode']}",
        f"Passed: {report['passed']}/{report['total']}",
        "",
        "| Query | Symbol | Identity | Total | Sources | Result |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in report["cases"]:
        selected = row.get("selected", {})
        lines.append(
            f"| {row['query']} | {selected.get('symbol', '')} | {row.get('identity_coverage', 0)}% | "
            f"{row.get('coverage_percent', 0)}% | {row.get('source_count', 0)} | "
            f"{'PASS' if row.get('passed') else 'FAIL'} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
