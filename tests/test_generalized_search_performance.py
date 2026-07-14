from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.providers import SYMBOL_UNIVERSE_PATH
from cdm_desktop.public_api.search_index_manager import SearchIndexManager
from cdm_desktop.public_api.search_query_plan import build_search_query_plan
from cdm_desktop.public_api.search_service import PublicSearchService


def _paths(root: Path) -> AppPaths:
    return AppPaths(root, root / "logs", root / "raw", root / "exports", root / "cache", root / "cdm.db").ensure()


def test_search_index_manager_is_process_scoped_and_thread_local() -> None:
    SearchIndexManager.reset_for_tests()
    first = SearchIndexManager.for_path(SYMBOL_UNIVERSE_PATH)
    second = SearchIndexManager.for_path(SYMBOL_UNIVERSE_PATH)
    assert first is second
    connection_ids: list[int] = []

    def connect() -> None:
        connection_ids.append(id(first.connection()))

    threads = [threading.Thread(target=connect) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(set(connection_ids)) == 2


def test_query_planner_routes_symbols_names_cjk_and_short_queries() -> None:
    assert build_search_query_plan("AAPL").query_type == "us_symbol"
    assert build_search_query_plan("AAPL").allow_fuzzy is False
    assert build_search_query_plan("General Electric Company").fts_terms
    chinese = build_search_query_plan("中国石油")
    assert chinese.scripts == ("cjk",)
    assert "中国" in chinese.ngrams
    assert build_search_query_plan("GE").allow_fuzzy is False


def test_bundled_indexes_have_fts_prefix_and_ngram_tables() -> None:
    connection = sqlite3.connect(f"{SYMBOL_UNIVERSE_PATH.resolve().as_uri()}?mode=ro", uri=True)
    try:
        sql = str(connection.execute("SELECT sql FROM sqlite_master WHERE name='symbols_fts'").fetchone()[0])
        assert "prefix='2 3 4'" in sql
        assert connection.execute("SELECT 1 FROM name_ngrams WHERE gram='app' LIMIT 1").fetchone()
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(name_ngrams)")}
        assert "idx_name_ngrams_gram" in indexes
    finally:
        connection.close()


def test_production_provider_has_no_leading_wildcard_or_alias_json_scan() -> None:
    text = (Path(__file__).parents[1] / "src/cdm_desktop/public_api/providers.py").read_text(encoding="utf-8")
    provider_block = text[text.index("class SymbolUniverseProvider") : text.index("class FinanceDatabaseProvider")]
    assert 'f"%{term}%"' not in provider_block
    assert "aliases_json LIKE" not in provider_block
    assert "symbols_fts MATCH ?" in provider_block


def test_query_cache_can_be_bypassed_and_cleared(tmp_path: Path) -> None:
    service = PublicSearchService(_paths(tmp_path))
    first = service.search_local("AAPL", use_cache=True)
    cached = service.search_local("AAPL", use_cache=True)
    bypassed = service.search_local("AAPL", use_cache=True, bypass_query_cache=True)
    assert first.companies
    assert cached.timing and cached.timing.cache_hit
    assert bypassed.timing and not bypassed.timing.cache_hit
    service.clear_query_cache()
    after_clear = service.search_local("AAPL", use_cache=True)
    assert after_clear.timing and not after_clear.timing.cache_hit


def test_shortlist_is_bounded_for_unseen_name(tmp_path: Path) -> None:
    service = PublicSearchService(_paths(tmp_path))
    response = service.search_local(
        "International Consolidated Airlines Group",
        bypass_query_cache=True,
        diagnostics_mode=True,
    )
    assert response.timing is not None
    assert response.timing.candidate_shortlist_size <= 200


def test_latin_global_query_does_not_run_china_index(tmp_path: Path) -> None:
    service = PublicSearchService(_paths(tmp_path))
    response = service.search_local("International Consolidated Airlines Group", bypass_query_cache=True)
    assert response.timing is not None
    assert "china_hk_symbol_index" not in response.timing.provider_timings


def test_benchmark_cache_isolated_from_default_appdata(tmp_path: Path) -> None:
    paths = _paths(tmp_path / "benchmark")
    service = PublicSearchService(paths)
    service.search_local("unseen benchmark isolation", use_cache=True)
    assert service.cache.paths.cache_dir.is_relative_to(tmp_path)
