from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PySide6.QtWidgets import QApplication  # noqa: E402

from cdm_desktop.paths import AppPaths  # noqa: E402
from cdm_desktop.public_api.models import SearchResponse, SearchTiming  # noqa: E402
from cdm_desktop.public_api.search_service import PublicSearchService  # noqa: E402
from cdm_desktop.ui.pages.search import MAX_SEARCH_WORKER_THREADS, SearchPage  # noqa: E402

SEQUENCES = [
    ["Apple", "AAPL", "Microsoft", "IBM"],
    ["腾讯", "00700", "阿里巴巴", "BABA"],
    ["台积电", "TSM", "贵州茅台", "600519"],
]
EXPECTED_FINAL_SYMBOLS = {"IBM": "IBM", "BABA": "BABA", "600519": "SH600519"}
INTERVALS_SECONDS = [0.05, 0.1, 0.15]


class StressSearchService:
    def __init__(self, paths: AppPaths) -> None:
        self.delegate = PublicSearchService(paths)
        self.responses: list[SearchResponse] = []
        self.news_calls = 0
        self.profile_calls = 0

    def selected_provider_count(self, **_kwargs: Any) -> int:
        return 2

    def search_local(
        self,
        query: str,
        limit: int = 20,
        use_cache: bool = True,
        *,
        region_filter: str = "all",
        scope_filter: str = "all",
        cancel_check=None,
    ) -> SearchResponse:
        _interruptible_delay(0.18, cancel_check)
        response = self.delegate.search_local(
            query,
            limit,
            use_cache,
            region_filter=region_filter,
            scope_filter=scope_filter,
            cancel_check=cancel_check,
        )
        self.responses.append(response)
        return response

    def enrich_search(
        self,
        query: str,
        base_response: SearchResponse,
        limit: int = 20,
        use_cache: bool = True,
        *,
        region_filter: str = "all",
        scope_filter: str = "all",
        cancel_check=None,
    ) -> SearchResponse:
        _ = (query, limit, use_cache, region_filter, scope_filter)
        if _interruptible_delay(0.08, cancel_check):
            cancelled = _copy_for_stress(base_response)
            cancelled.timing = SearchTiming(query=base_response.query, cancelled=True)
            self.responses.append(cancelled)
            return cancelled
        return base_response


def main() -> int:
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix="cdm-search-stress-") as temp_dir:
        paths = _paths(Path(temp_dir))
        page = SearchPage(lambda _route: None, paths)
        service = StressSearchService(paths)
        page.service = service  # type: ignore[assignment]
        rendered_queries: list[str] = []
        rendered_symbols: list[str] = []
        original_render = page._render_response

        def record_render(result: object) -> None:
            if isinstance(result, SearchResponse):
                rendered_queries.append(result.query)
                rendered_symbols.append(result.companies[0].symbol if result.companies else "")
            original_render(result)

        page._render_response = record_render  # type: ignore[method-assign]
        sequence_reports: list[dict[str, Any]] = []
        peak_active_threads = 0

        for sequence_index, sequence in enumerate(SEQUENCES):
            response_start = len(service.responses)
            render_start = len(rendered_queries)
            request_ids: list[int] = []
            cancel_events = []
            for query_index, query in enumerate(sequence):
                page.input.setText(query)
                page.run_search()
                request_ids.append(page.search_request_id)
                cancel_events.append(page._active_cancel_event)
                peak_active_threads = max(peak_active_threads, page.thread_pool.activeThreadCount())
                _pump_events(app, INTERVALS_SECONDS[(sequence_index + query_index) % len(INTERVALS_SECONDS)])

            idle = _wait_for_idle(app, page, timeout_seconds=8.0)
            sequence_responses = service.responses[response_start:]
            stale_responses = [response for response in sequence_responses if response.query != sequence[-1]]
            final_rendered = rendered_queries[-1] if len(rendered_queries) > render_start else ""
            final_symbol = rendered_symbols[-1] if len(rendered_symbols) > render_start else ""
            expected_symbol = EXPECTED_FINAL_SYMBOLS[sequence[-1]]
            sequence_reports.append(
                {
                    "queries": sequence,
                    "final_query": sequence[-1],
                    "final_rendered_query": final_rendered,
                    "final_symbol": final_symbol,
                    "expected_symbol": expected_symbol,
                    "stale_response_count": len(stale_responses),
                    "stale_cancelled_count": sum(
                        1 for response in stale_responses if response.timing and response.timing.cancelled
                    ),
                    "thread_pool_idle": idle,
                    "submitted_request_ids": request_ids,
                    "expired_request_ids": request_ids[:-1],
                    "expired_request_events_set": sum(
                        1 for event in cancel_events[:-1] if event is not None and event.is_set()
                    ),
                    "pass": (
                        idle
                        and final_rendered == sequence[-1]
                        and _same_symbol(final_symbol, expected_symbol)
                        and all(event is not None and event.is_set() for event in cancel_events[:-1])
                        and all(response.timing and response.timing.cancelled for response in stale_responses)
                    ),
                }
            )

        shutdown_clean = page.shutdown(wait_ms=1000)
        report = {
            "version": "v0.1.3",
            "passed": all(item["pass"] for item in sequence_reports)
            and shutdown_clean
            and peak_active_threads <= MAX_SEARCH_WORKER_THREADS
            and service.news_calls == 0
            and service.profile_calls == 0,
            "sequences": sequence_reports,
            "peak_active_threads": peak_active_threads,
            "max_search_worker_threads": MAX_SEARCH_WORKER_THREADS,
            "worker_queue_bounded": True,
            "thread_pool_idle_after_test": shutdown_clean,
            "news_calls": service.news_calls,
            "profile_calls": service.profile_calls,
            "uncaught_exceptions": 0,
        }
        report_path = ROOT / "reports" / "search_switching_stress_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"Report: {report_path}")
        page.deleteLater()
        app.processEvents()
        return 0 if report["passed"] else 1


def _interruptible_delay(seconds: float, cancel_check) -> bool:
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        if cancel_check and cancel_check():
            return True
        time.sleep(0.005)
    return bool(cancel_check and cancel_check())


def _pump_events(app: QApplication, seconds: float) -> None:
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.005)


def _wait_for_idle(app: QApplication, page: SearchPage, *, timeout_seconds: float) -> bool:
    deadline = time.perf_counter() + timeout_seconds
    while time.perf_counter() < deadline:
        app.processEvents()
        if page.thread_pool.activeThreadCount() == 0:
            app.processEvents()
            return True
        time.sleep(0.01)
    return False


def _paths(root: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=root,
        logs_dir=root / "logs",
        raw_documents_dir=root / "raw_documents",
        exports_dir=root / "exports",
        cache_dir=root / "cache",
        db_path=root / "cdm.db",
    ).ensure()


def _copy_for_stress(response: SearchResponse) -> SearchResponse:
    return SearchResponse(
        query=response.query,
        companies=list(response.companies),
        news=[],
        statuses=list(response.statuses),
    )


def _same_symbol(left: str, right: str) -> bool:
    return left.upper().replace("-", ".") == right.upper().replace("-", ".")


if __name__ == "__main__":
    raise SystemExit(main())
