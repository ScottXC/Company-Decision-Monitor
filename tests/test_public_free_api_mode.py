from __future__ import annotations

from pathlib import Path

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.cache import cache_key
from cdm_desktop.public_api.key_store import ApiKeyStore, mask_secret
from cdm_desktop.public_api.providers import (
    AlphaVantageProvider,
    FmpProvider,
    GleifProvider,
    MarketauxProvider,
    parse_alpha_symbol_search,
    parse_fmp_news,
    parse_fmp_search,
    parse_gleif_records,
    parse_marketaux_news,
    parse_nasdaq_directory,
)
from cdm_desktop.public_api.query import (
    acronym,
    fuzzy_score,
    normalize_query,
    remove_company_suffix,
)
from cdm_desktop.public_api.registry import ProviderRegistry
from cdm_desktop.public_api.search_service import PublicSearchService
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


def test_provider_not_configured_status(tmp_path: Path) -> None:
    service = PublicSearchService(make_paths(tmp_path))
    statuses = service.provider_statuses()
    fmp = next(item for item in statuses if item.provider_id == "fmp")

    assert fmp.state == "not_configured"
    assert "FMP_API_KEY" in fmp.message


def test_region_prefilter_selects_relevant_provider_subset(tmp_path: Path) -> None:
    service = PublicSearchService(make_paths(tmp_path))

    us_financial = service.selected_provider_ids(region_filter="us", scope_filter="financial")
    uk_entity = service.selected_provider_ids(region_filter="uk", scope_filter="entity")
    no_entity = service.selected_provider_ids(region_filter="no", scope_filter="entity")
    global_financial = service.selected_provider_ids(region_filter="global", scope_filter="financial")

    assert us_financial[:3] == ["nasdaq_directory", "fmp", "alpha_vantage"]
    assert "companies_house" not in us_financial
    assert uk_entity[:3] == ["companies_house", "opencorporates", "gleif"]
    assert no_entity[:3] == ["norway_brreg", "gleif", "opencorporates"]
    assert "nasdaq_directory" not in uk_entity
    assert "fmp" in global_financial
    assert "opencorporates" not in global_financial
    assert all("wikidata" not in providers for providers in [us_financial, uk_entity, no_entity, global_financial])


def test_wikipedia_provider_removed_from_production_registry() -> None:
    registry = ProviderRegistry()
    provider_ids = {item.provider_id for item in registry.all()}
    provider_names = {item.display_name for item in registry.all()}

    assert "wikidata" not in provider_ids
    assert "Wikidata / Wikipedia" not in provider_names


def test_fmp_mapping() -> None:
    rows = [{"symbol": "AAPL", "name": "Apple Inc.", "exchangeShortName": "NASDAQ"}]
    results = parse_fmp_search(rows, "Apple")

    assert results[0].symbol == "AAPL"
    assert results[0].provider_id == "fmp"
    assert results[0].match_score >= 80


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


def test_marketaux_and_fmp_news_mapping() -> None:
    marketaux = parse_marketaux_news(
        {"data": [{"title": "Company update", "source": "Example", "published_at": "2026-01-01", "url": "https://example.com"}]}
    )
    fmp = parse_fmp_news(
        [{"title": "FMP news", "site": "FMP", "publishedDate": "2026-01-01", "url": "https://example.com"}]
    )

    assert marketaux[0].provider == "Marketaux"
    assert fmp[0].provider == "Financial Modeling Prep"


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
