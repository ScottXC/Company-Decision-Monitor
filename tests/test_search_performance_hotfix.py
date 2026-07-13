from __future__ import annotations

import sqlite3
import sys
import time
import types
from pathlib import Path

from PySide6.QtCore import QThread
from scripts.benchmark_search import run_benchmark

import cdm_desktop.public_api.search_service as search_service_module
from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.cache import ApiCache
from cdm_desktop.public_api.key_store import ApiKeyStore
from cdm_desktop.public_api.models import CompanyResult, ProviderMeta, SearchResponse, SearchTiming
from cdm_desktop.public_api.providers import AkShareProvider, SymbolUniverseProvider
from cdm_desktop.public_api.registry import ProviderRegistry
from cdm_desktop.public_api.search_service import PublicSearchService
from cdm_desktop.ui.pages.search import DEBOUNCE_MS, MAX_SEARCH_WORKER_THREADS, SearchPage


def make_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        raw_documents_dir=tmp_path / "raw_documents",
        exports_dir=tmp_path / "exports",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "cdm.db",
    ).ensure()


def test_symbol_universe_has_search_indexes_and_alias_table() -> None:
    conn = sqlite3.connect(SymbolUniverseProvider.index_path)
    try:
        objects = {
            row[0]: row[1]
            for row in conn.execute("SELECT name, type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")
        }
    finally:
        conn.close()

    assert objects["symbols"] == "table"
    assert objects["aliases"] == "table"
    assert "idx_symbols_normalized_symbol" in objects
    assert "idx_symbols_normalized_name" in objects
    assert "idx_aliases_normalized_alias" in objects


def test_local_search_uses_bounded_shortlist_and_lru_cache(tmp_path: Path) -> None:
    service = PublicSearchService(make_paths(tmp_path))

    first = service.search_local("Apple", use_cache=True)
    cached = service.search_local("Apple", use_cache=True)

    assert first.companies[0].symbol == "AAPL"
    assert first.news == []
    assert first.timing is not None
    assert first.timing.candidate_shortlist_size <= 200
    assert cached.timing is not None
    assert cached.timing.cache_hit is True


def test_local_search_does_not_call_news_profile_or_public_providers(tmp_path: Path, monkeypatch) -> None:
    service = PublicSearchService(make_paths(tmp_path))
    called: list[str] = []
    original_provider = service._provider

    def tracking_provider(meta, *, enrichment: bool):
        called.append(meta.provider_id)
        return original_provider(meta, enrichment=enrichment)

    monkeypatch.setattr(service, "_provider", tracking_provider)
    response = service.search_local("AAPL", use_cache=False)

    assert response.news == []
    assert set(called) <= {"symbol_universe", "nasdaq_directory"}
    assert "akshare" not in called
    assert "wikidata" not in called
    assert "gleif" not in called
    assert "rss" not in called


def test_search_page_debounces_text_input(qtbot, tmp_path: Path, monkeypatch) -> None:
    page = SearchPage(lambda _route: None, make_paths(tmp_path))
    qtbot.addWidget(page)
    calls: list[str] = []
    monkeypatch.setattr(page, "_start_search", lambda: calls.append(page.input.text()))

    page.input.setText("Apple")
    assert calls == []
    qtbot.wait(DEBOUNCE_MS + 80)

    assert calls == ["Apple"]


def test_search_page_enter_bypasses_debounce(qtbot, tmp_path: Path, monkeypatch) -> None:
    page = SearchPage(lambda _route: None, make_paths(tmp_path))
    qtbot.addWidget(page)
    calls: list[str] = []
    monkeypatch.setattr(page, "_start_search", lambda: calls.append(page.input.text()))

    page.input.setText("Microsoft")
    page.input.returnPressed.emit()

    assert calls == ["Microsoft"]
    assert not page.debounce_timer.isActive()


def test_stale_request_result_is_discarded(qtbot, tmp_path: Path) -> None:
    page = SearchPage(lambda _route: None, make_paths(tmp_path))
    qtbot.addWidget(page)
    page.search_request_id = 2
    timing = SearchTiming(query="Apple")
    stale = SearchResponse(
        query="Apple",
        companies=[CompanyResult("Apple Inc.", "Index", "symbol_universe", symbol="AAPL")],
        news=[],
        statuses=[],
        timing=timing,
    )

    page._render_local_response((1, stale))

    assert timing.cancelled is True
    assert page._visible_company_keys == set()


def test_search_worker_does_not_run_on_ui_thread(qtbot, tmp_path: Path, monkeypatch) -> None:
    page = SearchPage(lambda _route: None, make_paths(tmp_path))
    qtbot.addWidget(page)
    ran_on_ui_thread: list[bool] = []
    response = SearchResponse(query="AAPL", companies=[], news=[], statuses=[])

    def local_search(*_args, **_kwargs):
        ran_on_ui_thread.append(QThread.currentThread() is page.thread())
        return response

    monkeypatch.setattr(page.service, "search_local", local_search)
    monkeypatch.setattr(page.service, "enrich_search", lambda *_args, **_kwargs: response)
    page.input.setText("AAPL")
    page.run_search()
    qtbot.waitUntil(lambda: bool(ran_on_ui_thread), timeout=2000)

    assert ran_on_ui_thread == [False]


def test_slow_public_provider_does_not_block_fast_result(tmp_path: Path, monkeypatch) -> None:
    service = PublicSearchService(make_paths(tmp_path))
    fast = ProviderMeta("wikidata", "Wikidata", "global", "", "", False, None, "", "", True)
    slow = ProviderMeta("gleif", "GLEIF", "global", "", "", False, None, "", "", True)
    monkeypatch.setattr(service, "_selected_providers", lambda *_args, **_kwargs: [fast, slow])
    monkeypatch.setattr(search_service_module, "PUBLIC_ENRICHMENT_BUDGET_SECONDS", 0.05)

    def fake_provider(meta, _query, _limit, _cancel_check=None):
        if meta.provider_id == "gleif":
            time.sleep(0.2)
            return [], None, 200.0
        return [CompanyResult("Apple Inc.", "Wikidata", "wikidata", wikidata_id="Q312")], None, 2.0

    monkeypatch.setattr(service, "_search_enrichment_provider", fake_provider)
    base = SearchResponse(query="Apple", companies=[], news=[], statuses=[])
    started = time.perf_counter()
    response = service.enrich_search("Apple", base, use_cache=False)

    assert time.perf_counter() - started < 0.15
    assert any(company.wikidata_id == "Q312" for company in response.companies)
    assert response.warnings


def test_search_page_worker_pool_is_bounded(qtbot, tmp_path: Path) -> None:
    page = SearchPage(lambda _route: None, make_paths(tmp_path))
    qtbot.addWidget(page)

    assert page.thread_pool.maxThreadCount() == MAX_SEARCH_WORKER_THREADS == 4


def test_cancelled_local_search_stops_before_ranking(tmp_path: Path, monkeypatch) -> None:
    service = PublicSearchService(make_paths(tmp_path))
    ranked = False

    def fail_if_ranked(*_args, **_kwargs):
        nonlocal ranked
        ranked = True
        raise AssertionError("cancelled search must not rank")

    monkeypatch.setattr(search_service_module, "rank_and_dedupe_companies", fail_if_ranked)
    response = service.search_local("Apple", use_cache=False, cancel_check=lambda: True)

    assert response.timing is not None and response.timing.cancelled is True
    assert ranked is False


def test_offline_local_index_finds_core_companies(tmp_path: Path) -> None:
    service = PublicSearchService(make_paths(tmp_path))

    assert service.search_local("AAPL", use_cache=False).companies[0].symbol == "AAPL"
    assert service.search_local("Apple", use_cache=False).companies[0].symbol == "AAPL"
    assert service.search_local("IBM", use_cache=False).companies[0].symbol == "IBM"
    assert service.search_local("腾讯", use_cache=False).companies[0].symbol in {"00700", "HK00700"}


def test_symbol_universe_runtime_uses_read_only_bounded_queries() -> None:
    source = (Path(__file__).parents[1] / "src" / "cdm_desktop" / "public_api" / "providers.py").read_text(encoding="utf-8")

    assert "mode=ro" in source
    assert "aliases_json LIKE" not in source
    assert "FUZZY_SHORTLIST_LIMIT = 200" in source


def test_akshare_symbol_lists_use_24_hour_cache(tmp_path: Path, monkeypatch) -> None:
    paths = make_paths(tmp_path)
    calls = {"cn": 0, "hk": 0}

    def load_cn():
        calls["cn"] += 1
        return [{"代码": "600519", "名称": "贵州茅台"}]

    def load_hk():
        calls["hk"] += 1
        return [{"代码": "700", "名称": "腾讯控股"}]

    monkeypatch.setitem(
        sys.modules,
        "akshare",
        types.SimpleNamespace(stock_info_a_code_name=load_cn, stock_hk_spot_em=load_hk),
    )
    meta = next(item for item in ProviderRegistry().all() if item.provider_id == "akshare")
    service_cache = ApiCache(paths)
    provider = AkShareProvider(meta, ApiKeyStore(paths), object(), service_cache)  # type: ignore[arg-type]

    provider.search("腾讯")
    provider.search("腾讯")

    assert calls == {"cn": 1, "hk": 1}
    assert service_cache.size_bytes() > 0


def test_cache_key_changes_with_filters(tmp_path: Path) -> None:
    service = PublicSearchService(make_paths(tmp_path))
    us = service.search_local("Apple", region_filter="us")
    hk = service.search_local("Apple", region_filter="hk")

    assert us.timing is not None and not us.timing.cache_hit
    assert hk.timing is not None and not hk.timing.cache_hit


def test_benchmark_local_thresholds() -> None:
    started = time.perf_counter()
    report = run_benchmark(measure_public=False)

    assert report["passed"] is True
    assert report["checks"]["warm_exact"] is True
    assert report["checks"]["warm_name"] is True
    assert report["checks"]["cache_hit"] is True
    assert time.perf_counter() - started < 15


def test_benchmark_script_contains_no_secret_output_contract() -> None:
    source = (Path(__file__).parents[1] / "scripts" / "benchmark_search.py").read_text(encoding="utf-8")

    assert "API_KEY" not in source
    assert "api_token" not in source
    assert "xq_a_token" not in source
