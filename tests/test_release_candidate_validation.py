from __future__ import annotations

from pathlib import Path

import httpx
from scripts.smoke_real_providers import _redact, _row

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.cache import ApiCache, cache_key
from cdm_desktop.public_api.http_client import PublicHttpClient
from cdm_desktop.public_api.key_store import ApiKeyStore, mask_secret
from cdm_desktop.public_api.models import CompanyResult
from cdm_desktop.public_api.providers import FmpProvider, parse_fmp_search
from cdm_desktop.public_api.registry import ProviderRegistry


def make_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        raw_documents_dir=tmp_path / "raw_documents",
        exports_dir=tmp_path / "exports",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "cdm.db",
    ).ensure()


def test_http_client_json_parse_error(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:  # noqa: ANN002
            return None

        def get(self, *args, **kwargs):  # noqa: ANN002, ANN003
            request = httpx.Request("GET", "https://example.com")
            return httpx.Response(200, content=b"not-json", request=request)

    monkeypatch.setattr(httpx, "Client", FakeClient)
    data, error = PublicHttpClient(retry_count=0).get_json("test", "https://example.com")

    assert data is None
    assert error is not None
    assert error.state == "parse_error"
    assert "Traceback" not in error.message


def test_http_client_timeout_error(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:  # noqa: ANN002
            return None

        def get(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(httpx, "Client", FakeClient)
    data, error = PublicHttpClient(retry_count=0).get_json("test", "https://example.com")

    assert data is None
    assert error is not None
    assert error.state == "network_timeout"
    assert "timeout" not in error.message.lower()


def test_provider_empty_and_not_configured_states(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    registry = ProviderRegistry()
    meta = next(item for item in registry.all() if item.provider_id == "fmp")
    provider = FmpProvider(meta, ApiKeyStore(paths), object())  # type: ignore[arg-type]

    companies, news, error = provider.search("AAPL")

    assert companies == []
    assert news == []
    assert error is not None
    assert error.state == "not_configured"
    assert "Traceback" not in error.message


def test_cache_fallback_miss(tmp_path: Path) -> None:
    cache = ApiCache(make_paths(tmp_path))
    key = cache_key("provider", "endpoint", {"apikey": "secret"}, "query")

    assert cache.get(key) is None
    assert cache.get_stale(key) is None


def test_smoke_report_row_and_redaction_do_not_leak_key(monkeypatch) -> None:
    monkeypatch.setenv("FMP_API_KEY", "real-secret-key")
    message = _redact("request failed for apikey=real-secret-key")
    row = _row("fmp", "check", "failed", message, key_mask=mask_secret("real-secret-key"))

    assert "real-secret-key" not in message
    assert "real-secret-key" not in str(row)
    assert row["key_mask"] == "real...-key"


def test_readme_docs_installer_do_not_contain_real_keys() -> None:
    paths = [
        Path("README.md"),
        Path("docs/release_notes.md"),
        Path("docs/external_sources.md"),
        Path("installer/CompanyDecisionMonitor.iss"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in paths)

    assert "real-secret-key" not in combined
    assert "demo-key" not in combined.lower()
    assert "xq_a_token" not in combined.lower()
    assert "PRIVATE KEY" not in combined


def test_provider_error_does_not_include_plain_api_key(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    store = ApiKeyStore(paths)
    store.set("FMP_API_KEY", "plain-secret-key")
    registry = ProviderRegistry()
    meta = next(item for item in registry.all() if item.provider_id == "fmp")

    class FakeHttp:
        def get_json(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return {"Error Message": "Invalid API KEY"}, None

    provider = FmpProvider(meta, store, FakeHttp())  # type: ignore[arg-type]
    _companies, _news, error = provider.search("AAPL")

    assert error is not None
    assert "plain-secret-key" not in error.message


def test_company_result_mapping_not_fake() -> None:
    rows = parse_fmp_search([{"symbol": "AAPL", "name": "Apple Inc."}], "AAPL")

    assert rows[0] == CompanyResult(
        name=rows[0].name,
        display_name=rows[0].display_name,
        symbol=rows[0].symbol,
        exchange=rows[0].exchange,
        market=rows[0].market,
        category=rows[0].category,
        provider=rows[0].provider,
        provider_id=rows[0].provider_id,
        source_url=rows[0].source_url,
        match_reason=rows[0].match_reason,
        match_score=rows[0].match_score,
        updated_at=rows[0].updated_at,
        raw=rows[0].raw,
    )
