from __future__ import annotations

from pathlib import Path

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.cache import ApiCache, cache_key
from cdm_desktop.public_api.models import CompanyProfile, CompanyResult, NewsItem, ProviderError
from cdm_desktop.public_api.news_service import _dedupe_news, _score_news
from cdm_desktop.public_api.profile_service import CompanyProfileService, _merge_profiles
from cdm_desktop.public_api.provider_health import ProviderHealthTracker
from cdm_desktop.public_api.query import (
    analyze_query,
    normalize_cn_symbol,
    normalize_hk_symbol,
    normalize_query,
    query_variants,
    remove_company_suffix,
)
from cdm_desktop.public_api.ranking import group_companies, rank_and_dedupe_companies, score_company
from cdm_desktop.public_api.seed_aliases import expand_query_aliases, seed_alias_exact_match
from cdm_desktop.public_api.watchlist_store import WatchlistStore


def make_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        raw_documents_dir=tmp_path / "raw_documents",
        exports_dir=tmp_path / "exports",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "cdm.db",
    ).ensure()


def test_query_normalizer_extended_cases() -> None:
    assert normalize_query(" Apple   Inc. ") == "apple inc"
    assert remove_company_suffix("Alibaba Group Holding Limited") == "alibaba"
    assert analyze_query("AAPL").kind == "us_symbol"
    assert analyze_query("BRK.B").symbol == "BRK.B"
    assert analyze_query("BRK-B").symbol == "BRK.B"
    assert normalize_hk_symbol("700") == "HK00700"
    assert normalize_hk_symbol("HK00700") == "HK00700"
    assert normalize_cn_symbol("600519") == "SH600519"
    assert normalize_cn_symbol("SZ000001") == "SZ000001"
    assert remove_company_suffix("腾讯控股") == "腾讯"


def test_seed_alias_expansion_for_chinese_and_abbreviations() -> None:
    assert {"HK00700", "Tencent"} <= set(expand_query_aliases({"腾讯"}))
    assert {"BABA", "HK09988"} <= set(expand_query_aliases({"阿里巴巴"}))
    assert {"TSM", "TSMC"} <= set(expand_query_aliases({"台积电"}))
    assert "BYD" in expand_query_aliases({"比亚迪"})
    assert "SH600519" in expand_query_aliases({"贵州茅台"})
    assert seed_alias_exact_match({"阿里巴巴"}, {"Alibaba Group", "BABA"})


def test_query_variants_do_not_return_seed_results_directly() -> None:
    variants = query_variants("腾讯", max_terms=6)

    assert "Tencent" in variants
    assert "HK00700" in variants
    assert all(isinstance(item, str) for item in variants)


def test_result_ranker_exact_symbol_beats_wikidata_weak_name() -> None:
    query = analyze_query("AAPL")
    ranked = rank_and_dedupe_companies(
        [
            CompanyResult("Apple", "Wikidata / Wikipedia", "wikidata", wikidata_id="Q312", match_score=88),
            CompanyResult("Apple Inc.", "Financial Modeling Prep", "fmp", symbol="AAPL", exchange="NASDAQ", match_score=65),
        ],
        query,
    )

    assert ranked[0].provider_id == "fmp"
    assert ranked[0].match_score == 100
    assert "代码完全匹配" in ranked[0].match_reason


def test_result_ranker_merges_multi_provider_sources() -> None:
    query = analyze_query("Apple")
    ranked = rank_and_dedupe_companies(
        [
            CompanyResult("Apple Inc.", "Financial Modeling Prep", "fmp", symbol="AAPL", exchange="NASDAQ", match_score=94),
            CompanyResult("Apple Inc.", "Alpha Vantage", "alpha_vantage", symbol="AAPL", exchange="NASDAQ", match_score=92),
        ],
        query,
    )

    assert len(ranked) == 1
    assert ranked[0].raw["provider_sources"] == ["alpha_vantage", "fmp"]
    assert ranked[0].match_score >= 97


def test_grouping_keeps_possible_matches_separate() -> None:
    items = [
        score_company(CompanyResult("Apple Inc.", "FMP", "fmp", symbol="AAPL", exchange="NASDAQ", match_score=98), analyze_query("Apple")),
        CompanyResult("Pineapple Holdings", "Wikidata", "wikidata", wikidata_id="QX", match_score=45),
    ]
    grouped = group_companies(items)

    assert len(grouped["best_matches"]) == 1
    assert grouped["possible_matches"][0].name == "Pineapple Holdings"


def test_news_relevance_scoring_and_dedupe() -> None:
    company = CompanyResult("Apple Inc.", "FMP", "fmp", symbol="AAPL", aliases=["Apple"])
    news = _score_news(
        [
            NewsItem("Apple announces supplier update", "Marketaux", provider_id="marketaux", source="Reuters", url="https://n/1", published_at="2026-01-02"),
            NewsItem("Generic market shares move", "FMP", provider_id="fmp", source="Blog", url="https://n/2", published_at="2026-01-03"),
            NewsItem("Apple announces supplier update", "FMP", provider_id="fmp", source="Other", url="https://n/3", published_at="2026-01-01"),
        ],
        company,
    )
    deduped = _dedupe_news(news)

    assert deduped[0].title.startswith("Apple")
    assert deduped[0].relevance_score > deduped[-1].relevance_score
    assert len([item for item in deduped if item.title.startswith("Apple")]) == 1


def test_company_profile_merge_priority_and_empty_values() -> None:
    company = CompanyResult("Apple Inc.", "Search", "nasdaq_directory", symbol="AAPL")
    merged = _merge_profiles(
        company,
        [
            CompanyProfile(display_name="Apple Inc.", market_cap="", website="", provider_sources=["fmp"]),
            CompanyProfile(market_cap="0", website="", provider_sources=["alpha_vantage"]),
            CompanyProfile(website="https://apple.com", description="Public entity", provider_sources=["wikidata"]),
            CompanyProfile(market_cap="3000000000000", provider_sources=["fmp"]),
        ],
    )

    assert merged.market_cap == "3000000000000"
    assert merged.website == "https://apple.com"
    assert merged.field_sources["market_cap"] == "fmp"
    assert merged.field_sources["website"] == "wikidata"


def test_watchlist_refresh_summary_partial_failure(tmp_path: Path, monkeypatch) -> None:
    paths = make_paths(tmp_path)
    store = WatchlistStore(paths)
    good = CompanyResult("Apple Inc.", "FMP", "fmp", symbol="AAPL")
    no_symbol = CompanyResult("GLEIF Entity", "GLEIF", "gleif", lei="529900T8BM49AURSDO55")
    store.add(good)
    store.add(no_symbol)

    def fake_profile(self, item):
        if item.lei:
            return None, []
        return CompanyProfile(display_name="Apple Inc.", symbol=item.symbol, provider_sources=["fmp"]), []

    monkeypatch.setattr(CompanyProfileService, "get_profile", fake_profile)
    summary = store.refresh_all_with_summary()

    assert summary.succeeded == 1
    assert summary.failed == 1
    assert len(summary.items) == 2


def test_provider_health_backoff_and_manual_bypass() -> None:
    tracker = ProviderHealthTracker(failure_threshold=2, backoff_seconds=30)
    error = ProviderError("fmp", "network_timeout", "timeout", retryable=True)

    tracker.record_error("fmp", "FMP", error)
    tracker.record_error("fmp", "FMP", error)

    assert tracker.should_skip("fmp", "FMP") is not None
    assert tracker.should_skip("fmp", "FMP", manual=True) is None
    tracker.record_success("fmp", "FMP")
    assert tracker.get("fmp").consecutive_failures == 0


def test_cache_corruption_ignored_and_clear(tmp_path: Path) -> None:
    cache = ApiCache(make_paths(tmp_path))
    key = cache_key("fmp", "profile", {"apikey": "plain-secret"}, "AAPL")
    path = cache._path(key)
    path.write_text("{bad-json", encoding="utf-8")

    assert "plain-secret" not in key
    assert cache.get(key) is None
    assert cache.get_stale(key) is None
    assert cache.clear() == 1


def test_xueqiu_not_news_or_scraping_marker() -> None:
    company = CompanyResult("Tencent", "FMP", "fmp", symbol="HK00700", aliases=["腾讯"])
    news = _score_news([], company)

    assert news == []
