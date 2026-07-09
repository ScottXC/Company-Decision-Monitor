from __future__ import annotations

# ruff: noqa: E402
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.news_service import CompanyNewsService
from cdm_desktop.public_api.profile_service import CompanyProfileService
from cdm_desktop.public_api.search_service import PublicSearchService
from cdm_desktop.public_api.watchlist_store import WatchlistStore

REPORTS = ROOT / "reports"
REPORT_PATH = REPORTS / "smoke_user_flow_report.json"


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
    for query in ("Apple", "AAPL", "IBM"):
        response = search.search(query, limit=5, region_filter="us")
        responses[query] = response
        steps.append(_step(f"search {query}", bool(response.companies or response.news), f"companies={len(response.companies)}, news={len(response.news)}, from_cache={response.from_cache}"))

    best = next((company for response in responses.values() for company in response.companies), None)
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

    refreshed_all = watchlist.refresh_all()
    steps.append(_step("refresh all watchlist items", len(refreshed_all) == 1, f"items={len(refreshed_all)}"))

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
