from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

from cdm_desktop import APP_MODE_LABEL, __version__
from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.key_store import ApiKeyStore
from cdm_desktop.public_api.providers import (
    AkShareProvider,
    FinanceDatabaseProvider,
    SymbolUniverseProvider,
    parse_akshare_records,
    parse_symbol_universe_records,
)
from cdm_desktop.public_api.query import fuzzy_score, remove_company_suffix
from cdm_desktop.public_api.registry import ProviderRegistry
from cdm_desktop.public_api.search_service import PublicSearchService
from cdm_desktop.public_api.settings_store import PublicApiSettingsStore


def make_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        raw_documents_dir=tmp_path / "raw_documents",
        exports_dir=tmp_path / "exports",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "cdm.db",
    ).ensure()


def test_open_source_data_mode_labels() -> None:
    assert __version__ == "0.1.4"
    assert APP_MODE_LABEL == "Open-Source Data Mode"


def test_advanced_api_providers_default_disabled(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    service = PublicSearchService(paths)
    provider_ids = service.selected_provider_ids()
    statuses = service.provider_statuses()
    fmp = next(item for item in statuses if item.provider_id == "fmp")

    assert "fmp" not in provider_ids
    assert "alpha_vantage" not in provider_ids
    assert "marketaux" not in provider_ids
    assert fmp.state == "disabled"
    assert "无需配置" in fmp.message


def test_advanced_api_providers_can_be_enabled_explicitly(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    PublicApiSettingsStore(paths).set_advanced_api_providers_enabled(True)
    service = PublicSearchService(paths)
    provider_ids = service.selected_provider_ids()

    assert "fmp" in provider_ids
    assert "alpha_vantage" in provider_ids
    assert "marketaux" in provider_ids


def test_registry_includes_open_source_providers_and_legacy_disabled() -> None:
    metas = {item.provider_id: item for item in ProviderRegistry().all()}

    assert not metas["symbol_universe"].requires_key
    assert metas["symbol_universe"].enabled_by_default
    assert not metas["finance_database"].enabled_by_default
    assert not metas["akshare"].requires_key
    assert not metas["fmp"].enabled_by_default
    assert not metas["alpha_vantage"].enabled_by_default
    assert not metas["marketaux"].enabled_by_default


def test_finance_database_dependency_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "financedatabase", None)
    meta = next(item for item in ProviderRegistry().all() if item.provider_id == "finance_database")
    provider = FinanceDatabaseProvider(meta, ApiKeyStore(make_paths(tmp_path)), object())  # type: ignore[arg-type]

    companies, _news, error = provider.search("AAPL")

    assert companies == []
    assert error is not None
    assert error.state == "dependency_missing"


def test_finance_database_mapping() -> None:
    rows = [
        {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "exchange": "NASDAQ",
            "country": "United States",
            "sector": "Technology",
        }
    ]
    results = parse_symbol_universe_records(rows, "Apple")

    assert results[0].symbol == "AAPL"
    assert results[0].provider_id == "finance_database"
    assert results[0].raw["from_local_index"] is True
    assert results[0].raw["is_realtime"] is False


def test_core_open_source_dependencies_available() -> None:
    assert importlib.util.find_spec("rapidfuzz") is not None
    assert importlib.util.find_spec("cleanco") is not None


def test_symbol_universe_index_exists_and_has_records() -> None:
    assert SymbolUniverseProvider.index_path.exists()
    import sqlite3

    conn = sqlite3.connect(SymbolUniverseProvider.index_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM symbol_universe").fetchone()[0]
    finally:
        conn.close()
    assert count > 1000


def test_symbol_universe_provider_exact_and_alias_search(tmp_path: Path) -> None:
    meta = next(item for item in ProviderRegistry().all() if item.provider_id == "symbol_universe")
    provider = SymbolUniverseProvider(meta, ApiKeyStore(make_paths(tmp_path)), object())  # type: ignore[arg-type]

    for query, expected in [
        ("AAPL", "AAPL"),
        ("Apple", "AAPL"),
        ("MSFT", "MSFT"),
        ("IBM", "IBM"),
        ("腾讯", "HK00700"),
        ("00700", "HK00700"),
        ("贵州茅台", "SH600519"),
        ("BRK.B", "BRK.B"),
    ]:
        companies, _news, error = provider.search(query, limit=5)
        assert error is None
        assert any(company.symbol == expected for company in companies), query


def test_akshare_dependency_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "akshare", None)
    meta = next(item for item in ProviderRegistry().all() if item.provider_id == "akshare")
    provider = AkShareProvider(meta, ApiKeyStore(make_paths(tmp_path)), object())  # type: ignore[arg-type]

    companies, _news, error = provider.search("贵州茅台")

    assert companies == []
    assert error is not None
    assert error.state == "dependency_missing"


def test_akshare_mapping() -> None:
    a_rows = [{"代码": "600519", "名称": "贵州茅台"}]
    hk_rows = [{"代码": "700", "名称": "腾讯控股"}]

    a_result = parse_akshare_records(a_rows, "茅台", market="CN")[0]
    hk_result = parse_akshare_records(hk_rows, "腾讯", market="HK")[0]

    assert a_result.symbol == "SH600519"
    assert a_result.exchange == "SSE"
    assert hk_result.symbol == "HK00700"
    assert hk_result.exchange == "HKEX"


def test_cleanco_normalization_optional(monkeypatch) -> None:
    import cdm_desktop.public_api.query as query_module

    monkeypatch.setattr(query_module, "cleanco_basename", lambda value: "Alibaba")

    assert remove_company_suffix("Alibaba Group Holding Limited") == "alibaba"


def test_difflib_fallback_when_rapidfuzz_missing(monkeypatch) -> None:
    import cdm_desktop.public_api.query as query_module

    monkeypatch.setattr(query_module, "rapidfuzz_fuzz", None)

    assert fuzzy_score("Apple", "Apple Inc.") >= 80


def test_finance_database_provider_with_mock_module(tmp_path: Path, monkeypatch) -> None:
    class FakeFrame:
        def reset_index(self):
            return self

        def to_dict(self, mode: str):
            assert mode == "records"
            return [{"symbol": "MSFT", "name": "Microsoft Corporation", "exchange": "NASDAQ"}]

    class FakeEquities:
        def select(self):
            return FakeFrame()

    fake_module = types.SimpleNamespace(Equities=FakeEquities)
    monkeypatch.setitem(sys.modules, "financedatabase", fake_module)
    meta = next(item for item in ProviderRegistry().all() if item.provider_id == "finance_database")
    provider = FinanceDatabaseProvider(meta, ApiKeyStore(make_paths(tmp_path)), object())  # type: ignore[arg-type]

    companies, _news, error = provider.search("Microsoft")

    assert error is None
    assert companies[0].symbol == "MSFT"
