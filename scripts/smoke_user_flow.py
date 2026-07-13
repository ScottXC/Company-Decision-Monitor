from __future__ import annotations

# ruff: noqa: E402
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.news_service import CompanyNewsService
from cdm_desktop.public_api.profile_service import CompanyProfileService
from cdm_desktop.public_api.search_service import PublicSearchService
from cdm_desktop.public_api.watchlist_store import WatchlistStore
from scripts.search_quality_lib import case_hit, load_search_cases, offline_search

REPORTS = ROOT / "reports"
REPORT_PATH = REPORTS / "smoke_user_flow_report.json"
SEARCH_SAMPLES = (
    "Apple",
    "AAPL",
    "IBM",
    "Microsoft",
    "Tencent",
    "腾讯",
    "00700",
    "Alibaba",
    "阿里巴巴",
    "BABA",
    "TSMC",
    "台积电",
    "TSM",
)


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cdm_smoke_") as tmp:
        paths = _paths(Path(tmp))
        report = _run_flow(paths)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_report(report)
    return 0 if report["summary"]["failed"] == 0 else 1


def _run_flow(paths: AppPaths) -> dict[str, Any]:
    search = PublicSearchService(paths)
    profile_service = CompanyProfileService(paths)
    news_service = CompanyNewsService(paths)
    watchlist = WatchlistStore(paths)
    steps: list[dict[str, Any]] = []

    responses = {}
    quality_cases = {str(case["query"]): case for case in load_search_cases()}
    for query in SEARCH_SAMPLES:
        region = "hk" if query in {"Tencent", "腾讯", "00700", "Alibaba", "阿里巴巴"} else "us"
        response = search.search(query, limit=5, region_filter=region)
        fallback_results = []
        if not response.companies:
            fallback_results, _diagnostics = offline_search(query)
        responses[query] = response
        warnings = len(response.warnings)
        errors = len(response.errors)
        expected_case = quality_cases.get(query)
        effective_companies = response.companies or fallback_results
        expected_hit = case_hit(effective_companies, expected_case, at=3) if expected_case else bool(effective_companies)
        top = effective_companies[0] if effective_companies else None
        fallback_used = bool(fallback_results) or response.from_cache or any(
            status.provider_id in {"nasdaq_directory", "wikidata", "gleif"} for status in response.statuses
        )
        steps.append(
            _step(
                f"search {query}",
                bool(response.companies or response.news or response.statuses),
                (
                    f"top={getattr(top, 'symbol', '') or getattr(top, 'name', '-')}, "
                    f"expected_hit={expected_hit}, provider_count={len(response.statuses)}, "
                    f"news={len(response.news)}, fallback_used={fallback_used}, "
                    f"from_cache={response.from_cache}, warnings={warnings}, errors={errors}"
                ),
            )
        )

    best = next((company for response in responses.values() for company in response.companies), None)
    if best is None:
        for query in SEARCH_SAMPLES:
            fallback_results, _diagnostics = offline_search(query)
            if fallback_results:
                best = fallback_results[0]
                break
    if best is None:
        steps.append(_step("select best result", False, "No company result returned by configured providers or fallbacks."))
        return {"steps": steps, "summary": _summary(steps)}

    profile, profile_statuses = profile_service.get_profile(best)
    steps.append(_step("open company detail", profile is not None or bool(profile_statuses), f"profile={bool(profile)}, statuses={len(profile_statuses)}"))

    news, news_statuses = news_service.get_news(best, limit=5)
    steps.append(_step("get related news", bool(news or news_statuses), f"news={len(news)}, statuses={len(news_statuses)}"))

    watchlist.add(best)
    steps.append(_step("add to temporary watchlist", len(watchlist.list_items()) == 1, f"items={len(watchlist.list_items())}"))

    refreshed = watchlist.refresh_item(best.dedupe_key())
    steps.append(_step("refresh one watchlist item", refreshed is not None, f"status={getattr(refreshed, 'last_status', '')}"))

    refresh_summary = watchlist.refresh_all_with_summary()
    steps.append(
        _step(
            "refresh all watchlist items",
            len(refresh_summary.items) == 1,
            (
                f"items={len(refresh_summary.items)}, success={refresh_summary.succeeded}, "
                f"failed={refresh_summary.failed}, from_cache={refresh_summary.from_cache}"
            ),
        )
    )

    watchlist.remove(best.dedupe_key())
    steps.append(_step("remove temporary watchlist item", len(watchlist.list_items()) == 0, f"items={len(watchlist.list_items())}"))
    return {"steps": steps, "summary": _summary(steps)}


def _paths(root: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=root,
        logs_dir=root / "logs",
        raw_documents_dir=root / "raw_documents",
        exports_dir=root / "exports",
        cache_dir=root / "cache",
        db_path=root / "cdm.db",
    ).ensure()


def _step(name: str, ok: bool, message: str) -> dict[str, Any]:
    return {"step": name, "status": "passed" if ok else "failed", "message": message}


def _summary(steps: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "passed": sum(1 for item in steps if item["status"] == "passed"),
        "failed": sum(1 for item in steps if item["status"] == "failed"),
    }


def _print_report(report: dict[str, Any]) -> None:
    print("User-flow smoke test")
    for step in report["steps"]:
        print(f"- {step['step']} | {step['status']} | {step['message']}")
    print(f"Summary: {report['summary']}")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    sys.exit(main())
