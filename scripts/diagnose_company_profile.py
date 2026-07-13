from __future__ import annotations

# ruff: noqa: E402
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for entry in (ROOT, SRC):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from cdm_desktop.public_api.data_quality import is_meaningful_value, profile_coverage
from cdm_desktop.public_api.profile_service import CompanyProfileService
from cdm_desktop.public_api.search_service import PublicSearchService


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose the company-profile enrichment pipeline.")
    parser.add_argument("query")
    parser.add_argument("--local", action="store_true", help="Only inspect search-result and bundled-index fields.")
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()

    started = time.perf_counter()
    search = PublicSearchService().search_local(args.query, limit=5)
    selected = search.companies[0] if search.companies else None
    if not selected:
        report = {"query": args.query, "error": "No company result was selected.", "search_results": []}
    else:
        service = CompanyProfileService()
        initial = service.get_immediate_profile(selected)
        if args.local:
            profile, statuses = initial, []
        else:
            profile, statuses = service.get_profile(selected)
        fields = profile.to_dict() if profile else {}
        report = {
            "query": args.query,
            "search_results": [item.to_dict() for item in search.companies[:5]],
            "selected_company": selected.to_dict(),
            "provider_call_plan": service._provider_order(selected),
            "initial_fields": _populated(initial.to_dict()),
            "provider_statuses": [
                {
                    "provider": status.provider_id,
                    "state": status.state,
                    "message": status.message,
                }
                for status in statuses
            ],
            "merged_fields": _populated(fields),
            "provider_fields": _provider_fields(profile.field_sources if profile else {}),
            "field_sources": profile.field_sources if profile else {},
            "coverage": profile_coverage(profile).to_dict() if profile else {},
            "unresolved_fields": profile.missing_fields if profile else [],
            "from_cache": bool(profile and profile.from_cache),
            "total_duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    if args.json_path:
        output = Path(args.json_path)
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if selected else 1


def _populated(data: dict[str, Any]) -> dict[str, Any]:
    excluded = {"raw", "field_candidates"}
    return {key: value for key, value in data.items() if key not in excluded and is_meaningful_value(value, key)}


def _provider_fields(field_sources: dict[str, str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for field, provider in field_sources.items():
        grouped.setdefault(provider, []).append(field)
    return grouped


if __name__ == "__main__":
    raise SystemExit(main())
