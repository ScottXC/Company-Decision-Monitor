from __future__ import annotations

from pathlib import Path

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.models import CompanyResult
from cdm_desktop.public_api.providers import XueqiuExternalLinkProvider
from cdm_desktop.public_api.registry import ProviderRegistry
from cdm_desktop.public_api.search_service import PublicSearchService
from cdm_desktop.public_api.xueqiu_external_link import (
    XUEQIU_HOME_URL,
    build_xueqiu_external_link,
    normalize_xueqiu_symbol,
)


def make_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        raw_documents_dir=tmp_path / "raw_documents",
        exports_dir=tmp_path / "exports",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "cdm.db",
    ).ensure()


def test_xueqiu_a_share_symbol_links() -> None:
    assert normalize_xueqiu_symbol(symbol="600519") == "SH600519"
    assert normalize_xueqiu_symbol(symbol="SH600519") == "SH600519"
    assert normalize_xueqiu_symbol(symbol="000001") == "SZ000001"
    assert normalize_xueqiu_symbol(symbol="SZ000001") == "SZ000001"


def test_xueqiu_hk_symbol_links() -> None:
    assert normalize_xueqiu_symbol(symbol="700") == "HK00700"
    assert normalize_xueqiu_symbol(symbol="00700") == "HK00700"
    assert normalize_xueqiu_symbol(symbol="HK00700") == "HK00700"
    assert normalize_xueqiu_symbol(symbol="9988") == "HK09988"


def test_xueqiu_us_symbol_links() -> None:
    assert normalize_xueqiu_symbol(symbol="AAPL") == "AAPL"
    assert normalize_xueqiu_symbol(symbol="TSLA") == "TSLA"
    assert normalize_xueqiu_symbol(symbol="MSFT") == "MSFT"


def test_xueqiu_unknown_market_falls_back_to_homepage() -> None:
    no_symbol = build_xueqiu_external_link(company_name="Unknown Company")
    company_name_only = build_xueqiu_external_link(symbol="", company_name="Only Name")

    assert no_symbol.url == XUEQIU_HOME_URL
    assert company_name_only.url == XUEQIU_HOME_URL
    assert not no_symbol.is_direct_stock_link
    assert "External link only" in no_symbol.compliance_note


def test_xueqiu_provider_does_not_call_http() -> None:
    class FailingHttp:
        def get_json(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("Xueqiu external link provider must not call HTTP")

        def get_text(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("Xueqiu external link provider must not call HTTP")

    meta = next(item for item in ProviderRegistry().all() if item.provider_id == "xueqiu_external")
    provider = XueqiuExternalLinkProvider(meta, object(), FailingHttp())  # type: ignore[arg-type]
    companies, news, error = provider.search("AAPL")
    link = provider.build_link(CompanyResult("Apple Inc.", "FMP", "fmp", symbol="AAPL"))

    assert companies == []
    assert news == []
    assert error is None
    assert link.url == "https://xueqiu.com/S/AAPL"
    assert "/query/" not in link.url
    assert "/v5/stock/" not in link.url
    assert not link.url.endswith(".json")


def test_xueqiu_registry_status_is_external_link_without_key(tmp_path: Path) -> None:
    registry = ProviderRegistry()
    meta = next(item for item in registry.all() if item.provider_id == "xueqiu_external")
    status = next(item for item in PublicSearchService(make_paths(tmp_path)).provider_statuses() if item.provider_id == "xueqiu_external")

    assert meta.category == "external_link"
    assert not meta.requires_key
    assert status.state == "enabled"
    assert "news" not in meta.category


def test_xueqiu_ui_text_is_compliance_oriented() -> None:
    company_detail = Path("src/cdm_desktop/ui/pages/company_detail.py").read_text(encoding="utf-8")
    search_page = Path("src/cdm_desktop/ui/pages/search.py").read_text(encoding="utf-8")
    combined = company_detail + search_page

    assert "外部链接" in combined
    assert "不抓取内容" in combined
    assert "雪球新闻已抓取" not in combined
    assert "正在同步雪球" not in combined
    assert "cookie" not in combined.lower()
    assert "xq_a_token" not in combined.lower()


def test_xueqiu_docs_state_external_source_boundaries() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    docs = Path("docs/external_sources.md").read_text(encoding="utf-8")

    assert "Xueqiu Community Entry" in readme
    assert "not scrape" in readme
    assert "does not use user cookies or tokens" in readme
    assert "cookie input" not in readme.lower()
    assert "token input" not in readme.lower()
    assert "no scraping" in docs.lower()
    assert "no unofficial api" in docs.lower()
