from __future__ import annotations

from pathlib import Path

import cdm_desktop.public_api.search_service as search_module
from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.cache import ApiCache, cache_key
from cdm_desktop.public_api.key_store import ApiKeyStore, mask_secret
from cdm_desktop.public_api.models import CompanyProfile, CompanyResult, NewsItem
from cdm_desktop.public_api.news_service import _dedupe_news
from cdm_desktop.public_api.profile_service import CompanyProfileService, _merge_profiles
from cdm_desktop.public_api.providers import (
    AlphaVantageProvider,
    FmpProvider,
    GleifProvider,
    MarketauxProvider,
    _alpha_payload_error,
    _fmp_payload_error,
    _marketaux_payload_error,
    parse_alpha_overview,
    parse_alpha_symbol_search,
    parse_fmp_news,
    parse_fmp_profile,
    parse_fmp_search,
    parse_gleif_records,
    parse_marketaux_news,
    parse_nasdaq_directory,
    parse_wikidata_profile,
    parse_wikidata_search,
)
from cdm_desktop.public_api.query import (
    acronym,
    fuzzy_score,
    normalize_query,
    remove_company_suffix,
)
from cdm_desktop.public_api.registry import ProviderRegistry
from cdm_desktop.public_api.search_service import PublicSearchService
from cdm_desktop.public_api.settings_store import PublicApiSettingsStore
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


def test_api_key_mask_save_read_clear(tmp_path: Path) -> None:
    store = ApiKeyStore(make_paths(tmp_path))
    store.set("FMP_API_KEY", "abcd1234efgh5678")

    assert store.get("FMP_API_KEY") == "abcd1234efgh5678"
    assert mask_secret(store.get("FMP_API_KEY")) == "abcd...5678"

    store.clear("FMP_API_KEY")
    assert store.get("FMP_API_KEY") == ""


def test_cache_key_does_not_include_plain_api_key() -> None:
    key = cache_key("fmp", "/search", {"apikey": "secret-value", "query": "Apple"}, "Apple")

    assert "secret-value" not in key
    assert len(key) == 64


def test_cache_fallback_can_read_stale_payload(tmp_path: Path) -> None:
    cache = ApiCache(make_paths(tmp_path))
    key = cache_key("test", "endpoint", {"apikey": "secret-value"}, "Apple")
    cache.set(key, {"ok": True}, ttl_seconds=-1)

    assert cache.get(key) is None
    assert cache.get_stale(key) == {"ok": True}


def test_provider_not_configured_status(tmp_path: Path) -> None:
    service = PublicSearchService(make_paths(tmp_path))
    statuses = service.provider_statuses()
    fmp = next(item for item in statuses if item.provider_id == "fmp")

    assert fmp.state == "disabled"
    assert "普通用户无需配置" in fmp.message


def test_region_prefilter_selects_relevant_provider_subset(tmp_path: Path) -> None:
    service = PublicSearchService(make_paths(tmp_path))

    us_financial = service.selected_provider_ids(region_filter="us", scope_filter="financial")
    uk_entity = service.selected_provider_ids(region_filter="uk", scope_filter="entity")
    no_entity = service.selected_provider_ids(region_filter="no", scope_filter="entity")
    global_financial = service.selected_provider_ids(region_filter="global", scope_filter="financial")

    assert us_financial[:3] == ["symbol_universe", "nasdaq_directory"]
    assert "companies_house" not in us_financial
    assert uk_entity[:2] == ["wikidata", "gleif"]
    assert no_entity[:3] == ["norway_brreg", "wikidata", "gleif"]
    assert "nasdaq_directory" not in uk_entity
    assert "symbol_universe" in global_financial
    assert "fmp" not in global_financial
    assert "wikidata" not in us_financial
    assert "wikidata" in uk_entity


def test_wikidata_provider_is_available_as_fallback() -> None:
    registry = ProviderRegistry()
    provider_ids = {item.provider_id for item in registry.all()}
    provider_names = {item.display_name for item in registry.all()}

    assert "wikidata" in provider_ids
    assert "Wikidata / Wikipedia" in provider_names


def test_fmp_mapping() -> None:
    rows = [{"symbol": "AAPL", "name": "Apple Inc.", "exchangeShortName": "NASDAQ"}]
    results = parse_fmp_search(rows, "Apple")

    assert results[0].symbol == "AAPL"
    assert results[0].provider_id == "fmp"
    assert results[0].match_score >= 80


def test_fmp_profile_mapping() -> None:
    profile = parse_fmp_profile(
        [
            {
                "symbol": "AAPL",
                "companyName": "Apple Inc.",
                "price": 123.45,
                "mktCap": 123456,
                "currency": "USD",
                "exchangeShortName": "NASDAQ",
                "industry": "Consumer Electronics",
                "sector": "Technology",
                "country": "US",
                "website": "https://www.apple.com",
                "description": "Apple profile",
                "ceo": "CEO",
                "fullTimeEmployees": "100000",
                "isEtf": False,
            }
        ]
    )

    assert profile is not None
    assert profile.symbol == "AAPL"
    assert profile.market_cap == "123456"
    assert profile.field_sources["market_cap"] == "fmp"


def test_fmp_error_mapping() -> None:
    invalid = _fmp_payload_error({"Error Message": "Invalid API KEY"}, "fmp")
    quota = _fmp_payload_error({"message": "Limit Reach. Please upgrade."}, "fmp")

    assert invalid is not None
    assert invalid.state == "invalid_key"
    assert quota is not None
    assert quota.state in {"quota_exceeded", "premium_endpoint"}


def test_alpha_vantage_mapping() -> None:
    payload = {
        "bestMatches": [
            {
                "1. symbol": "IBM",
                "2. name": "International Business Machines",
                "3. type": "Equity",
                "4. region": "United States",
            }
        ]
    }
    results = parse_alpha_symbol_search(payload, "IBM")

    assert results[0].symbol == "IBM"
    assert results[0].provider_id == "alpha_vantage"


def test_alpha_vantage_overview_mapping_and_error_mapping() -> None:
    profile = parse_alpha_overview(
        {
            "Symbol": "IBM",
            "Name": "International Business Machines",
            "Description": "IBM profile",
            "CIK": "51143",
            "Exchange": "NYSE",
            "Currency": "USD",
            "Country": "USA",
            "Sector": "Technology",
            "Industry": "Information Technology Services",
            "MarketCapitalization": "1000000",
            "PERatio": "12.3",
        }
    )
    note = _alpha_payload_error({"Note": "standard API call frequency is 5 calls per minute"}, "alpha_vantage")
    info = _alpha_payload_error({"Information": "daily rate limit reached"}, "alpha_vantage")
    invalid = _alpha_payload_error({"Error Message": "Invalid API call"}, "alpha_vantage")

    assert profile is not None
    assert profile.symbol == "IBM"
    assert profile.raw["PERatio"] == "12.3"
    assert note is not None and note.state == "rate_limited"
    assert info is not None and info.state == "quota_exceeded"
    assert invalid is not None and invalid.state == "invalid_key"


def test_marketaux_and_fmp_news_mapping() -> None:
    marketaux = parse_marketaux_news(
        {"data": [{"title": "Company update", "source": "Example", "published_at": "2026-01-01", "url": "https://example.com"}]}
    )
    fmp = parse_fmp_news(
        [{"title": "FMP news", "site": "FMP", "publishedDate": "2026-01-01", "url": "https://example.com"}]
    )

    assert marketaux[0].provider == "Marketaux"
    assert fmp[0].provider == "Financial Modeling Prep"


def test_marketaux_news_rich_mapping_and_error_mapping() -> None:
    news = parse_marketaux_news(
        {
            "data": [
                {
                    "uuid": "n1",
                    "title": "Company update",
                    "description": "Short summary",
                    "url": "https://example.com/news",
                    "image_url": "https://example.com/img.png",
                    "published_at": "2026-01-01T00:00:00Z",
                    "source": {"name": "Example News"},
                    "entities": [{"symbol": "AAPL"}],
                    "sentiment_score": 0.2,
                    "language": "en",
                    "country": "us",
                }
            ]
        }
    )
    invalid = _marketaux_payload_error({"error": "Invalid api_token"}, "marketaux")
    quota = _marketaux_payload_error({"error": "quota exceeded"}, "marketaux")

    assert news[0].id == "n1"
    assert news[0].source == "Example News"
    assert news[0].sentiment_score == 0.2
    assert invalid is not None and invalid.state == "invalid_key"
    assert quota is not None and quota.state == "quota_exceeded"


def test_gleif_mapping() -> None:
    payload = {
        "data": [
            {
                "id": "529900T8BM49AURSDO55",
                "attributes": {
                    "entity": {
                        "legalName": {"name": "Example Legal Entity"},
                        "jurisdiction": "US",
                        "legalAddress": {"country": "US"},
                    }
                },
            }
        ]
    }
    results = parse_gleif_records(payload, "Example")

    assert results[0].lei == "529900T8BM49AURSDO55"
    assert results[0].provider_id == "gleif"


def test_nasdaq_directory_parsing() -> None:
    text = "Symbol|Security Name|Market Category|Test Issue\nAAPL|Apple Inc.|Q|N\nZVZZT|Test|Q|Y\n"
    results = parse_nasdaq_directory(text, "AAPL")

    assert results[0].symbol == "AAPL"
    assert results[0].provider_id == "nasdaq_directory"


def test_wikidata_mapping() -> None:
    results = parse_wikidata_search(
        {
            "search": [
                {
                    "id": "Q312",
                    "label": "Apple Inc.",
                    "description": "American technology company",
                    "aliases": ["Apple"],
                }
            ]
        },
        "Apple",
    )
    profile = parse_wikidata_profile(
        {
            "entities": {
                "Q312": {
                    "labels": {"en": {"value": "Apple Inc."}},
                    "descriptions": {"en": {"value": "American technology company"}},
                    "sitelinks": {"enwiki": {"title": "Apple Inc."}},
                }
            }
        },
        "Q312",
    )

    assert results[0].wikidata_id == "Q312"
    assert results[0].aliases == ["Apple"]
    assert profile is not None
    assert profile.wikipedia_url.endswith("Apple_Inc.")


def test_query_normalizer_and_fuzzy() -> None:
    assert normalize_query(" Apple, Inc. ") == "apple inc"
    assert remove_company_suffix("Apple Inc") == "apple"
    assert acronym("International Business Machines") == "IBM"
    assert fuzzy_score("IBM", "International Business Machines") >= 90


def test_watchlist_persistence(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    store = WatchlistStore(paths)
    company = parse_fmp_search([{"symbol": "AAPL", "name": "Apple Inc."}], "Apple")[0]

    store.add(company)
    store.add(company)

    assert len(store.list_items()) == 1
    store.remove(company.dedupe_key())
    assert store.list_items() == []


def test_watchlist_refresh_single_and_all(tmp_path: Path, monkeypatch) -> None:
    paths = make_paths(tmp_path)
    store = WatchlistStore(paths)
    company = parse_fmp_search([{"symbol": "AAPL", "name": "Apple Inc."}], "Apple")[0]
    store.add(company)

    def fake_profile(self, item):
        return (
            CompanyProfile(
                display_name="Apple Inc.",
                symbol=item.symbol,
                exchange="NASDAQ",
                country="US",
                provider_sources=["fmp"],
            ),
            [],
        )

    monkeypatch.setattr(CompanyProfileService, "get_profile", fake_profile)

    refreshed = store.refresh_item(company.dedupe_key())
    assert refreshed is not None
    assert refreshed.last_status == "refreshed"
    assert refreshed.last_refreshed_at
    assert store.refresh_all()[0].exchange == "NASDAQ"


def test_company_profile_merge_keeps_field_sources() -> None:
    company = CompanyResult("Apple Inc.", "Nasdaq Symbol Directory", "nasdaq_directory", symbol="AAPL")
    merged = _merge_profiles(
        company,
        [
            CompanyProfile(display_name="Apple Inc.", symbol="AAPL", market_cap="1000", provider_sources=["fmp"]),
            CompanyProfile(description="Technology company", website="https://apple.com", provider_sources=["wikidata"]),
        ],
    )

    assert merged.market_cap == "1000"
    assert merged.description == "Technology company"
    assert merged.field_sources["market_cap"] == "fmp"
    assert merged.field_sources["description"] == "wikidata"


def test_company_news_dedupe() -> None:
    news = _dedupe_news(
        [
            NewsItem("Same title", "Marketaux", provider_id="marketaux", source="A", url="https://example.com/1", published_at="2026-01-02"),
            NewsItem("Same title", "FMP", provider_id="fmp", source="B", url="https://example.com/1", published_at="2026-01-01"),
            NewsItem("Other title", "FMP", provider_id="fmp", source="B", url="https://example.com/2", published_at="2026-01-03"),
        ]
    )

    assert [item.url for item in news] == ["https://example.com/2", "https://example.com/1"]


def test_company_search_service_aggregates_and_dedupes(tmp_path: Path, monkeypatch) -> None:
    paths = make_paths(tmp_path)
    service = PublicSearchService(paths)
    metas = {item.provider_id: item for item in service.registry.all()}
    service.registry.providers = [metas["fmp"], metas["alpha_vantage"], metas["marketaux"]]
    ApiKeyStore(paths).set("FMP_API_KEY", "fmp-key")
    ApiKeyStore(paths).set("ALPHA_VANTAGE_API_KEY", "alpha-key")
    ApiKeyStore(paths).set("MARKETAUX_API_KEY", "marketaux-key")
    PublicApiSettingsStore(paths).set_advanced_api_providers_enabled(True)

    class FakeProvider:
        def __init__(self, provider_id: str) -> None:
            self.provider_id = provider_id

        def search(self, query: str, limit: int = 10):
            if self.provider_id == "marketaux":
                return [], [NewsItem("Apple news", "Marketaux", provider_id="marketaux", url="https://news.example")], None
            provider = "Financial Modeling Prep" if self.provider_id == "fmp" else "Alpha Vantage"
            return [CompanyResult("Apple Inc.", provider, self.provider_id, symbol="AAPL", exchange="NASDAQ", match_score=95)], [], None

    monkeypatch.setattr(search_module, "provider_for", lambda meta, _keys, _http, _cache: FakeProvider(meta.provider_id))

    response = service.search("Apple", region_filter="all")

    assert len(response.companies) == 1
    assert response.companies[0].provider_id == "fmp"
    # Company search never loads news; news is detail-on-demand.
    assert response.news == []
    assert response.grouped_results["best_matches"]


def test_missing_key_provider_does_not_call_http(tmp_path: Path) -> None:
    registry = ProviderRegistry()
    meta = next(item for item in registry.all() if item.provider_id == "fmp")
    provider = FmpProvider(meta, ApiKeyStore(make_paths(tmp_path)), object())  # type: ignore[arg-type]

    companies, news, error = provider.search("Apple")

    assert companies == []
    assert news == []
    assert error is not None
    assert error.state == "not_configured"


def test_provider_classes_exported(tmp_path: Path) -> None:
    registry = ProviderRegistry()
    metas = {item.provider_id: item for item in registry.all()}
    paths = make_paths(tmp_path)
    key_store = ApiKeyStore(paths)
    fake_http = object()

    assert FmpProvider(metas["fmp"], key_store, fake_http).meta.requires_key  # type: ignore[arg-type]
    assert AlphaVantageProvider(metas["alpha_vantage"], key_store, fake_http).meta.requires_key  # type: ignore[arg-type]
    assert MarketauxProvider(metas["marketaux"], key_store, fake_http).meta.requires_key  # type: ignore[arg-type]
    assert not GleifProvider(metas["gleif"], key_store, fake_http).meta.requires_key  # type: ignore[arg-type]

