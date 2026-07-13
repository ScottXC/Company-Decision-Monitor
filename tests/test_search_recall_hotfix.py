from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.diagnose_search import _offline_report
from scripts.evaluate_search_quality import _evaluate_offline
from scripts.search_quality_lib import case_hit, load_news_cases, load_search_cases, offline_search

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.key_store import ApiKeyStore
from cdm_desktop.public_api.models import CompanyResult, NewsItem, ProviderError
from cdm_desktop.public_api.news_service import (
    CompanyNewsService,
    _dedupe_news,
    _filter_relevant_news,
    _score_news,
    build_news_query_terms,
)
from cdm_desktop.public_api.query import analyze_query, normalize_cn_symbol, normalize_hk_symbol
from cdm_desktop.public_api.ranking import group_companies, rank_and_dedupe_companies


def make_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        raw_documents_dir=tmp_path / "raw_documents",
        exports_dir=tmp_path / "exports",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "cdm.db",
    ).ensure()


def test_search_quality_cases_pass_offline() -> None:
    failures = []
    for case in load_search_cases():
        results, _diagnostics = offline_search(case["query"])
        if not case_hit(results, case, at=3):
            failures.append((case["query"], [item.to_dict() for item in results[:3]]))

    assert failures == []


def test_news_quality_cases_build_expected_terms() -> None:
    for case in load_news_cases():
        company = CompanyResult(
            name=case["company_name"],
            display_name=case["company_name"],
            symbol=case["symbol"],
            aliases=list(case["aliases"]),
            provider="fixture",
            provider_id="fixture",
        )
        terms = set(build_news_query_terms(company))
        for expected in case["expected_query_terms"]:
            assert expected in terms


def test_diagnose_search_default_report_redacts_and_has_details() -> None:
    report = _offline_report("腾讯")
    text = json.dumps(report, ensure_ascii=False)

    assert report["detected_query_type"] == "name"
    assert "HK00700" in text
    assert "apikey=" not in text
    assert "api_token=" not in text


def test_evaluate_search_quality_default_mode_passes() -> None:
    report = _evaluate_offline()

    assert report["summary"]["failed"] == 0
    assert report["summary"]["recall_at_3"] == 1.0


def test_search_quality_script_default_runs() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/evaluate_search_quality.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "Search quality evaluation" in completed.stdout


def test_market_symbol_detection_extended_cases() -> None:
    assert normalize_hk_symbol("700") == "HK00700"
    assert normalize_hk_symbol("9988") == "HK09988"
    assert normalize_hk_symbol("5") == "HK00005"
    assert normalize_cn_symbol("600519") == "SH600519"
    assert normalize_cn_symbol("000001") == "SZ000001"
    assert normalize_cn_symbol("300750") == "SZ300750"
    assert analyze_query("BRK.B").symbol == "BRK.B"
    assert analyze_query("BRK-B").symbol == "BRK.B"


def test_chinese_alias_results_enter_best_matches() -> None:
    results, _diagnostics = offline_search("阿里巴巴")
    grouped = group_companies(results)

    assert grouped["best_matches"]
    assert grouped["best_matches"][0].symbol in {"BABA", "HK09988"}


def test_ranking_exact_symbol_beats_weak_wikidata_and_etf_lowered() -> None:
    ranked = rank_and_dedupe_companies(
        [
            CompanyResult("Apple", "Wikidata", "wikidata", wikidata_id="Q312", match_score=92),
            CompanyResult("Apple Inc.", "FMP", "fmp", symbol="AAPL", exchange="NASDAQ", match_score=65),
        ],
        analyze_query("AAPL"),
    )
    name_ranked = rank_and_dedupe_companies(
        [
            CompanyResult("Apple ETF", "Nasdaq", "nasdaq_directory", symbol="AAPLX", exchange="NASDAQ", raw={"is_etf": True}, match_score=90),
            CompanyResult("Apple Inc.", "FMP", "fmp", symbol="AAPL", exchange="NASDAQ", match_score=80),
        ],
        analyze_query("Apple"),
    )

    assert ranked[0].symbol == "AAPL"
    assert name_ranked[-1].name == "Apple ETF"


def test_possible_match_excluded_from_best_matches() -> None:
    grouped = group_companies(
        [
            CompanyResult("Apple Inc.", "FMP", "fmp", symbol="AAPL", exchange="NASDAQ", match_score=95),
            CompanyResult("Pineapple", "Wikidata", "wikidata", wikidata_id="QX", match_score=45),
        ]
    )

    assert all(item.name != "Pineapple" for item in grouped["best_matches"])
    assert grouped["possible_matches"][0].name == "Pineapple"


def test_dedup_merges_provider_sources_for_symbols_wikidata_and_lei() -> None:
    symbol_ranked = rank_and_dedupe_companies(
        [
            CompanyResult("Apple Inc.", "FMP", "fmp", symbol="AAPL", exchange="NASDAQ", match_score=94),
            CompanyResult("Apple Inc.", "Alpha", "alpha_vantage", symbol="AAPL", exchange="NASDAQ", match_score=92),
        ],
        analyze_query("Apple"),
    )
    wikidata_ranked = rank_and_dedupe_companies(
        [
            CompanyResult("Apple", "Wikidata", "wikidata", wikidata_id="Q312", match_score=80),
            CompanyResult("Apple Inc.", "Wikidata", "wikidata", wikidata_id="Q312", match_score=82),
        ],
        analyze_query("Apple"),
    )
    lei_ranked = rank_and_dedupe_companies(
        [
            CompanyResult("Entity A", "GLEIF", "gleif", lei="529900T8BM49AURSDO55", match_score=80),
            CompanyResult("Entity A Ltd", "GLEIF", "gleif", lei="529900T8BM49AURSDO55", match_score=85),
        ],
        analyze_query("529900T8BM49AURSDO55"),
    )

    assert len(symbol_ranked) == 1
    assert symbol_ranked[0].raw["provider_sources"] == ["alpha_vantage", "fmp"]
    assert len(wikidata_ranked) == 1
    assert len(lei_ranked) == 1


def test_news_service_falls_back_from_symbol_to_company_name(tmp_path: Path, monkeypatch) -> None:
    paths = make_paths(tmp_path)
    ApiKeyStore(paths).set("MARKETAUX_API_KEY", "not-a-real-key")
    calls = []

    class FakeProvider:
        def __init__(self, provider_id: str) -> None:
            self.provider_id = provider_id

        def news(self, *, symbol: str = "", company_name: str = "", limit: int = 20):  # noqa: ANN001
            calls.append((symbol, company_name))
            if symbol:
                return [], ProviderError(self.provider_id, "empty", "empty")
            if "Apple" in company_name:
                return [
                    NewsItem(
                        "Apple Inc. expands services",
                        "Marketaux",
                        provider_id="marketaux",
                        source="Reuters",
                        published_at="2026-01-01",
                        url="https://news.example/apple?utm_source=x",
                        snippet="Apple Inc. update",
                    )
                ], None
            return [], ProviderError(self.provider_id, "empty", "empty")

    def fake_provider_for(meta, *args):  # noqa: ANN001
        return FakeProvider(meta.provider_id)

    monkeypatch.setattr("cdm_desktop.public_api.news_service.provider_for", fake_provider_for)
    company = CompanyResult("Apple Inc.", "FMP", "fmp", symbol="AAPL", aliases=["Apple"])
    news, _statuses = CompanyNewsService(paths).get_news(company)

    assert calls[0][0] == "AAPL"
    assert any(name in {"Apple", "Apple Inc."} for _symbol, name in calls)
    assert len(news) == 1
    assert news[0].relevance_score >= 40


def test_news_dedupe_filters_unrelated_and_xueqiu_external() -> None:
    company = CompanyResult("Apple Inc.", "FMP", "fmp", symbol="AAPL", aliases=["Apple"])
    scored = _score_news(
        [
            NewsItem("Apple Inc. expands services", "Marketaux", provider_id="marketaux", source="Reuters", url="https://x/a?utm_source=y", snippet="Apple update"),
            NewsItem("Apple Inc. expands services", "FMP", provider_id="fmp", source="Other", url="https://x/a", snippet="Apple update"),
            NewsItem("Generic market shares", "FMP", provider_id="fmp", source="Blog", url="https://x/b"),
            NewsItem("Open Xueqiu", "Xueqiu", provider_id="xueqiu_external", source="Xueqiu", url="https://xueqiu.com/S/AAPL"),
        ],
        company,
    )
    filtered = _filter_relevant_news(scored)
    deduped = _dedupe_news(filtered)

    assert len(deduped) == 1
    assert deduped[0].provider_id == "marketaux"
    assert all(item.provider_id != "xueqiu_external" for item in deduped)
