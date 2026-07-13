from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtWidgets import QLabel

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.data_quality import is_meaningful_value, profile_coverage
from cdm_desktop.public_api.models import CompanyProfile, CompanyResult, NewsItem
from cdm_desktop.public_api.profile_service import (
    PROFILE_SCHEMA_VERSION,
    CompanyProfileService,
    _merge_profiles,
)
from cdm_desktop.public_api.providers import GleifProvider, SymbolUniverseProvider, WikidataProvider
from cdm_desktop.public_api.query import analyze_query
from cdm_desktop.public_api.ranking import rank_and_dedupe_companies
from cdm_desktop.public_api.registry import ProviderRegistry
from cdm_desktop.ui.pages.company_detail import CompanyDetailPage


def make_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        raw_documents_dir=tmp_path / "raw_documents",
        exports_dir=tmp_path / "exports",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "cdm.db",
    ).ensure()


def meta(provider_id: str):
    return next(item for item in ProviderRegistry().all() if item.provider_id == provider_id)


def test_company_profile_extended_schema_round_trip_and_old_cache() -> None:
    profile = CompanyProfile(
        id="1",
        display_name="Apple Inc.",
        legal_name="Apple Inc.",
        aliases=["Apple"],
        symbol="AAPL",
        instrument_type="equity",
        registration_status="ISSUED",
        legal_address="Cupertino",
        field_candidates={"website": [{"value": "https://example.test", "provider": "test"}]},
    )
    restored = CompanyProfile.from_dict(profile.to_dict())

    assert restored == profile
    legacy = CompanyProfile.from_dict({"display_name": "Legacy", "symbol": "OLD", "zip_code": "10001"})
    assert legacy.schema_version == 1
    assert legacy.postal_code == "10001"


def test_meaningful_values_and_zero_semantics() -> None:
    for value in (None, "", "  ", "None", "null", "N/A", "-", "--", "unknown", "暂无数据"):
        assert not is_meaningful_value(value)
    assert not is_meaningful_value(0, "price")
    assert is_meaningful_value(0, "registration_number")


def test_profile_coverage_uses_entity_specific_templates() -> None:
    listed = CompanyProfile(
        display_name="Listed",
        symbol="LIST",
        exchange="XNAS",
        market="US",
        country="US",
        currency="USD",
        instrument_type="equity",
        company_type="listed_company",
    )
    legal = CompanyProfile(
        display_name="Legal Entity",
        legal_name="LEGAL ENTITY LTD",
        lei="529900TEST000000000",
        jurisdiction="GB",
        country="GB",
        company_type="legal_entity",
    )
    encyclopedia = CompanyProfile(
        display_name="Entity",
        description="Public entity",
        wikidata_id="Q1",
        wikipedia_url="https://example.test/wiki",
        company_type="encyclopedia_entity",
    )

    assert profile_coverage(listed).identity_coverage == 100
    assert profile_coverage(legal).identity_coverage == 100
    assert profile_coverage(legal).market_coverage == 0
    assert "symbol" not in profile_coverage(legal).unresolved_fields
    assert profile_coverage(encyclopedia).identity_coverage == 100
    assert "exchange" not in profile_coverage(encyclopedia).unresolved_fields


def test_local_symbol_profile_reads_bundled_index(tmp_path: Path) -> None:
    service = CompanyProfileService(make_paths(tmp_path))
    profile = service.get_immediate_profile(
        CompanyResult("Apple", "Index", "symbol_universe", symbol="AAPL")
    )

    assert profile.display_name == "Apple Inc."
    assert profile.exchange == "NMS"
    assert profile.country == "United States"
    assert profile.currency == "USD"
    assert profile.sector
    assert profile.industry
    assert profile.instrument_type == "equity"
    assert profile.field_sources["country"] == "symbol_universe"
    assert profile_coverage(profile).identity_coverage >= 70


def test_local_symbol_provider_reports_missing_index(tmp_path: Path) -> None:
    service = CompanyProfileService(make_paths(tmp_path))
    provider = SymbolUniverseProvider(meta("symbol_universe"), service.key_store, service.http, service.cache)
    provider.index_path = tmp_path / "missing.sqlite"

    profile, error = provider.profile(CompanyResult("Apple", "Index", "symbol_universe", symbol="AAPL"))

    assert profile is None
    assert error and error.state == "index_missing"


class WikidataHttp:
    def get_json(self, _provider, _url, *, params=None, **_kwargs):
        if params and params.get("action") == "wbsearchentities":
            return {
                "search": [
                    {
                        "id": "Q312",
                        "label": "Apple Inc.",
                        "description": "American technology company",
                        "aliases": ["Apple"],
                    }
                ]
            }, None
        return {
            "entities": {
                "Q312": {
                    "labels": {"en": {"value": "Apple Inc."}},
                    "descriptions": {"en": {"value": "American technology company"}},
                    "aliases": {"en": [{"value": "Apple"}]},
                    "claims": {
                        "P856": [{"mainsnak": {"datavalue": {"value": "https://www.apple.com"}}}],
                        "P249": [{"mainsnak": {"datavalue": {"value": "AAPL"}}}],
                    },
                    "sitelinks": {"enwiki": {"title": "Apple Inc."}},
                }
            }
        }, None


def test_wikidata_resolves_entity_without_qid(tmp_path: Path) -> None:
    service = CompanyProfileService(make_paths(tmp_path))
    provider = WikidataProvider(meta("wikidata"), service.key_store, WikidataHttp(), service.cache)

    profile, error = provider.profile(CompanyResult("Apple Inc.", "Index", "symbol_universe", symbol="AAPL"))

    assert error is None
    assert profile and profile.wikidata_id == "Q312"
    assert profile.website == "https://www.apple.com"
    assert profile.symbol == "AAPL"


class AmbiguousWikidataHttp(WikidataHttp):
    def get_json(self, _provider, _url, *, params=None, **_kwargs):
        if params and params.get("action") == "wbsearchentities":
            return {"search": [{"id": "Q1", "label": "Unrelated", "description": "topic"}]}, None
        return super().get_json(_provider, _url, params=params, **_kwargs)


def test_wikidata_rejects_low_confidence_entity(tmp_path: Path) -> None:
    service = CompanyProfileService(make_paths(tmp_path))
    provider = WikidataProvider(meta("wikidata"), service.key_store, AmbiguousWikidataHttp(), service.cache)

    profile, error = provider.profile(CompanyResult("Apple Inc.", "Index", "symbol_universe", symbol="AAPL"))

    assert profile is None
    assert error and error.state == "empty"


class NonOrganizationWikidataHttp:
    def get_json(self, _provider, _url, **_kwargs):
        return {
            "entities": {
                "QBAD": {
                    "labels": {"en": {"value": "Tencent"}},
                    "descriptions": {"en": {"value": "weather station in Western Australia"}},
                    "aliases": {},
                    "claims": {},
                    "sitelinks": {},
                }
            }
        }, None


def test_wikidata_rejects_exact_name_non_organization(tmp_path: Path) -> None:
    service = CompanyProfileService(make_paths(tmp_path))
    provider = WikidataProvider(
        meta("wikidata"), service.key_store, NonOrganizationWikidataHttp(), service.cache
    )

    profile, error = provider.profile(
        CompanyResult(
            "Tencent Holding Ltd.",
            "Index",
            "symbol_universe",
            symbol="HK00700",
            wikidata_id="QBAD",
            aliases=["Tencent"],
        )
    )

    assert profile is None
    assert error and "未自动采用" in error.message


class GleifHttp:
    def get_json(self, _provider, url, **_kwargs):
        record = {
            "id": "HWUPKR0MPOU8FGXBT394",
            "attributes": {
                "lei": "HWUPKR0MPOU8FGXBT394",
                "entity": {
                    "legalName": {"name": "APPLE INC."},
                    "jurisdiction": "US-CA",
                    "status": "ACTIVE",
                    "category": "GENERAL",
                    "legalAddress": {
                        "addressLines": ["One Apple Park Way"],
                        "city": "Cupertino",
                        "region": "US-CA",
                        "postalCode": "95014",
                        "country": "US",
                    },
                },
                "registration": {"status": "ISSUED"},
            },
        }
        return ({"data": record} if url.endswith("HWUPKR0MPOU8FGXBT394") else {"data": [record]}), None


def test_gleif_resolves_legal_name_without_lei(tmp_path: Path) -> None:
    service = CompanyProfileService(make_paths(tmp_path))
    provider = GleifProvider(meta("gleif"), service.key_store, GleifHttp(), service.cache)

    profile, error = provider.profile(CompanyResult("Apple Inc.", "Index", "symbol_universe", symbol="AAPL"))

    assert error is None
    assert profile and profile.lei == "HWUPKR0MPOU8FGXBT394"
    assert profile.registration_status == "ISSUED"
    assert "Cupertino" in profile.legal_address


class WrongSubsidiaryGleifHttp(GleifHttp):
    def get_json(self, _provider, url, **_kwargs):
        data, error = super().get_json(_provider, url, **_kwargs)
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            record = data["data"][0]
            record["attributes"]["entity"]["legalName"]["name"] = "APPLE OPERATIONS INTERNATIONAL LIMITED"
            record["attributes"]["entity"]["legalAddress"]["country"] = "IE"
        return data, error


def test_gleif_rejects_wrong_country_subsidiary(tmp_path: Path) -> None:
    service = CompanyProfileService(make_paths(tmp_path))
    provider = GleifProvider(meta("gleif"), service.key_store, WrongSubsidiaryGleifHttp(), service.cache)

    profile, error = provider.profile(
        CompanyResult("Apple Inc.", "Index", "symbol_universe", symbol="AAPL", country="United States")
    )

    assert profile is None
    assert error and error.state == "empty"


def test_profile_merge_does_not_replace_good_values_with_empty() -> None:
    merged = _merge_profiles(
        CompanyResult("Apple", "Index", "symbol_universe", symbol="AAPL"),
        [
            CompanyProfile(website="https://apple.com", provider_sources=["wikidata"]),
            CompanyProfile(website="N/A", market_cap="0", provider_sources=["fmp"]),
        ],
    )

    assert merged.website == "https://apple.com"
    assert not merged.market_cap
    assert merged.field_sources["website"] == "wikidata"


def test_chinese_byd_alias_does_not_rank_boyd_gaming_first() -> None:
    ranked = rank_and_dedupe_companies(
        [
            CompanyResult(
                "Boyd Gaming Corporation",
                "Index",
                "symbol_universe",
                symbol="BYD",
                exchange="NYSE",
            ),
            CompanyResult(
                "BYD Co., Ltd.",
                "Index",
                "symbol_universe",
                symbol="HK01211",
                exchange="HKEX",
            ),
        ],
        analyze_query("比亚迪"),
    )

    assert ranked[0].name == "BYD Co., Ltd."
    assert ranked[0].match_reason == "高置信别名匹配"


def test_profile_cache_key_includes_schema(tmp_path: Path) -> None:
    service = CompanyProfileService(make_paths(tmp_path))
    company = CompanyResult("Apple", "Index", "symbol_universe", symbol="AAPL")
    key = service._profile_cache_key(company)

    assert key
    assert PROFILE_SCHEMA_VERSION == 4


def test_old_empty_profile_cache_is_ignored_without_touching_watchlist(tmp_path: Path) -> None:
    service = CompanyProfileService(make_paths(tmp_path))
    company = CompanyResult("Apple", "Index", "symbol_universe", symbol="AAPL")
    key = service._profile_cache_key(company)
    service.cache.set(key, {"schema_version": 1, "display_name": ""}, ttl_seconds=3600)
    service._provider_order = lambda _company: ["symbol_universe"]

    profile, _statuses = service.get_profile(company)

    assert profile and profile.display_name == "Apple Inc."
    assert not profile.from_cache


def test_company_detail_rerenders_profile_without_reloading_news(qtbot, tmp_path: Path) -> None:
    page = CompanyDetailPage(lambda _route: None, make_paths(tmp_path))
    qtbot.addWidget(page)
    news_calls = 0

    def fake_news(_company, _limit=12):
        nonlocal news_calls
        news_calls += 1
        return [], []

    page.news_service.get_news = fake_news
    page.profile_service.get_profile = lambda _company: (page.profile_service.get_immediate_profile(_company), [])
    page.set_company(CompanyResult("Apple", "Index", "symbol_universe", symbol="AAPL"))
    page.refresh()
    qtbot.waitUntil(lambda: news_calls == 1)
    page.tabs.setCurrentIndex(2)
    before = news_calls
    profile = CompanyProfile(
        display_name="Apple Inc.",
        legal_name="APPLE INC.",
        symbol="AAPL",
        exchange="NASDAQ",
        website="https://apple.com",
        description="Technology company",
        registration_status="ISSUED",
        provider_sources=["wikidata", "gleif"],
        data_coverage={"coverage_percent": 60},
    )
    page._render_profile_result((profile, []))

    assert page.tabs.currentIndex() == 2
    labels = [label.text() for label in page.findChildren(QLabel)]
    assert "Technology company" in labels
    assert "https://apple.com" in labels
    assert "ISSUED" in labels
    assert news_calls == before
    assert page.shutdown(wait_ms=5000)


def test_company_detail_empty_registry_uses_single_empty_state(qtbot, tmp_path: Path) -> None:
    page = CompanyDetailPage(lambda _route: None, make_paths(tmp_path))
    qtbot.addWidget(page)
    page.set_company(CompanyResult("No Registry", "Index", "symbol_universe", symbol="ZZZZ"))
    page.profile_service.get_profile = lambda _company: (CompanyProfile(display_name="No Registry"), [])
    page.news_service.get_news = lambda _company, _limit=12: ([], [])
    page.refresh()

    labels = [label.text() for label in page.tabs.widget(2).findChildren(QLabel)]
    assert "暂无法人注册资料" in labels
    assert page.shutdown(wait_ms=5000)


def test_stale_profile_and_news_results_do_not_replace_new_company(qtbot, tmp_path: Path) -> None:
    page = CompanyDetailPage(lambda _route: None, make_paths(tmp_path))
    qtbot.addWidget(page)
    page.profile_service.get_profile = lambda company: (
        CompanyProfile(display_name=company.name, symbol=company.symbol, provider_sources=["test"]),
        [],
    )
    page.news_service.get_news = lambda _company, _limit=12: ([], [])

    page.set_company(CompanyResult("Apple Inc.", "Index", "symbol_universe", symbol="AAPL"))
    page.refresh()
    old_request_id = page._detail_request_id
    page.set_company(CompanyResult("Microsoft Corporation", "Index", "symbol_universe", symbol="MSFT"))
    page.refresh()
    new_request_id = page._detail_request_id

    page._handle_profile_result(
        old_request_id,
        (CompanyProfile(display_name="Stale Apple", symbol="AAPL", provider_sources=["test"]), []),
    )
    page._handle_news_result(
        old_request_id,
        ([NewsItem("Stale Apple news", "test")], []),
    )

    assert new_request_id != old_request_id
    assert page.current_company and page.current_company.symbol == "MSFT"
    assert all(label.text() != "Stale Apple" for label in page.findChildren(QLabel))
    assert all(label.text() != "Stale Apple news" for label in page.findChildren(QLabel))
    assert page.shutdown(wait_ms=5000)


def test_profile_worker_runs_off_ui_thread(qtbot, tmp_path: Path) -> None:
    page = CompanyDetailPage(lambda _route: None, make_paths(tmp_path))
    qtbot.addWidget(page)
    main_thread = threading.get_ident()
    worker_threads: list[int] = []
    finished = threading.Event()

    def fake_profile(company):
        worker_threads.append(threading.get_ident())
        finished.set()
        return CompanyProfile(display_name=company.name, symbol=company.symbol), []

    page.profile_service.get_profile = fake_profile
    page.news_service.get_news = lambda _company, _limit=12: ([], [])
    page.set_company(CompanyResult("Apple Inc.", "Index", "symbol_universe", symbol="AAPL"))
    page.refresh()
    qtbot.waitUntil(finished.is_set)

    assert worker_threads and worker_threads[0] != main_thread
    assert page.shutdown(wait_ms=5000)


def test_shutdown_rejects_late_detail_results(qtbot, tmp_path: Path) -> None:
    page = CompanyDetailPage(lambda _route: None, make_paths(tmp_path))
    qtbot.addWidget(page)
    page.set_company(CompanyResult("Microsoft", "Index", "symbol_universe", symbol="MSFT"))
    page.profile_service.get_profile = lambda company: (CompanyProfile(display_name=company.name), [])
    page.news_service.get_news = lambda _company, _limit=12: ([], [])
    page.refresh()
    request_id = page._detail_request_id
    page.shutdown()

    page._handle_profile_result(
        request_id,
        (CompanyProfile(display_name="Late result", symbol="LATE"), []),
    )

    assert page.current_company and page.current_company.symbol == "MSFT"
