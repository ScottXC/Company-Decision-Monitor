from __future__ import annotations

# ruff: noqa: E402
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cdm_desktop.paths import get_app_paths
from cdm_desktop.public_api.cache import ApiCache
from cdm_desktop.public_api.http_client import PublicHttpClient
from cdm_desktop.public_api.key_store import ApiKeyStore, mask_secret
from cdm_desktop.public_api.models import CompanyResult, ProviderError
from cdm_desktop.public_api.providers import provider_for
from cdm_desktop.public_api.registry import ProviderRegistry

REPORTS = ROOT / "reports"
REPORT_PATH = REPORTS / "smoke_provider_report.json"
SEARCH_SAMPLES = (
    "Apple",
    "AAPL",
    "IBM",
    "Microsoft",
    "Tencent",
    "腾讯",
    "00700",
    "Alibaba",
    "阿里巴巴",
    "BABA",
    "TSMC",
    "台积电",
    "TSM",
)
FAIL_STATES = {"invalid_key", "parse_error"}
WARN_STATES = {
    "not_configured",
    "rate_limited",
    "quota_exceeded",
    "premium_endpoint",
    "network_timeout",
    "dns_failure",
    "http_error",
    "provider_unavailable",
    "empty",
    "cache_miss",
    "dependency_missing",
}


class RuntimeKeyStore:
    def __init__(self) -> None:
        self.app_store = ApiKeyStore()
        self.dotenv = _read_dotenv(ROOT / ".env")

    def get(self, key_name: str | None) -> str:
        if not key_name:
            return ""
        return os.environ.get(key_name) or self.dotenv.get(key_name) or self.app_store.get(key_name)

    def status(self, key_name: str | None) -> tuple[bool, str]:
        if not key_name:
            return True, "not required"
        value = self.get(key_name)
        return bool(value), mask_secret(value)


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    registry = ProviderRegistry()
    key_store = RuntimeKeyStore()
    cache = ApiCache(get_app_paths())
    http = PublicHttpClient()
    results: list[dict[str, Any]] = []

    provider_ids = [
        "symbol_universe",
        "akshare",
        "nasdaq_directory",
        "wikidata",
        "gleif",
        "fmp",
        "alpha_vantage",
        "marketaux",
    ]
    for provider_id in provider_ids:
        meta = next((item for item in registry.all() if item.provider_id == provider_id), None)
        if meta is None:
            continue
        configured, masked = key_store.status(meta.key_name)
        if meta.requires_key and not configured:
            results.append(_row(provider_id, "configuration", "skipped", f"{meta.key_name} not configured", key_mask=masked))
            continue
        provider = provider_for(meta, key_store, http, cache)  # type: ignore[arg-type]
        _run_provider_checks(provider_id, provider, results, masked)

    report = {
        "version": "v0.1.4-generalized-search-performance-rc1",
        "mode": "Open-Source Data Mode",
        "search_samples": SEARCH_SAMPLES,
        "results": results,
        "summary": _summary(results),
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_report(report)

    if any(item["status"] == "failed" for item in results):
        return 1
    return 0


def _run_provider_checks(provider_id: str, provider, results: list[dict[str, Any]], key_mask: str) -> None:  # noqa: ANN001
    try:
        if provider_id in {"symbol_universe", "akshare"}:
            for sample in ("Apple", "AAPL", "Tencent", "腾讯", "00700", "贵州茅台"):
                companies, _news, error = provider.search(sample, limit=5)
                _record_result(results, provider_id, f"search {sample}", companies, error, key_mask)
        elif provider_id == "fmp":
            _record_error(results, provider_id, "test_connection", provider.test_connection(), key_mask)
            for sample in ("AAPL", "Apple", "BABA"):
                companies, _news, error = provider.search(sample, limit=3)
                _record_result(results, provider_id, f"search {sample}", companies, error, key_mask)
            profile, error = provider.profile(CompanyResult("Apple Inc.", "Financial Modeling Prep", "fmp", symbol="AAPL"))
            _record_result(results, provider_id, "profile AAPL", [profile] if profile else [], error, key_mask)
            news, error = provider.news(symbol="AAPL", company_name="Apple", limit=5)
            _record_result(results, provider_id, "news AAPL", news, error, key_mask)
        elif provider_id == "alpha_vantage":
            _record_error(results, provider_id, "test_connection", provider.test_connection(), key_mask)
            for sample in ("IBM", "MSFT", "TSM"):
                companies, _news, error = provider.search(sample, limit=3)
                _record_result(results, provider_id, f"SYMBOL_SEARCH {sample}", companies, error, key_mask)
            profile, error = provider.profile(CompanyResult("IBM", "Alpha Vantage", "alpha_vantage", symbol="IBM"))
            _record_result(results, provider_id, "OVERVIEW IBM", [profile] if profile else [], error, key_mask)
        elif provider_id == "marketaux":
            _record_error(results, provider_id, "test_connection", provider.test_connection(), key_mask)
            news, error = provider.news(symbol="AAPL", company_name="Apple", limit=5)
            _record_result(results, provider_id, "news AAPL", news, error, key_mask)
        elif provider_id == "nasdaq_directory":
            for sample in ("AAPL", "Apple", "IBM", "Microsoft", "TSM"):
                companies, _news, error = provider.search(sample, limit=5)
                _record_result(results, provider_id, f"search {sample}", companies, error, key_mask)
        elif provider_id == "wikidata":
            companies, _news, error = provider.search("Apple Inc.", limit=5)
            _record_result(results, provider_id, "search Apple Inc.", companies, error, key_mask)
            if companies:
                profile, error = provider.profile(companies[0])
                _record_result(results, provider_id, "profile fallback", [profile] if profile else [], error, key_mask)
            for sample in ("Tencent", "阿里巴巴", "台积电"):
                companies, _news, error = provider.search(sample, limit=3)
                _record_result(results, provider_id, f"search {sample}", companies, error, key_mask)
        elif provider_id == "gleif":
            companies, _news, error = provider.search("Microsoft", limit=5)
            _record_result(results, provider_id, "name search Microsoft", companies, error, key_mask)
    except Exception as exc:  # noqa: BLE001
        results.append(_row(provider_id, "program exception", "failed", _redact(str(exc))))


def _record_error(results: list[dict[str, Any]], provider_id: str, check: str, error: ProviderError | None, key_mask: str) -> None:
    if error:
        status = _status_from_error(error)
        results.append(_row(provider_id, check, status, _redact(error.message), error_state=error.state, key_mask=key_mask))
    else:
        results.append(_row(provider_id, check, "passed", "connection check passed", key_mask=key_mask))


def _record_result(
    results: list[dict[str, Any]],
    provider_id: str,
    check: str,
    rows: list[Any],
    error: ProviderError | None,
    key_mask: str,
) -> None:
    if error:
        status = _status_from_error(error)
        results.append(_row(provider_id, check, status, _redact(error.message), error_state=error.state, key_mask=key_mask))
        return
    status = "passed" if rows else "warning"
    message = f"returned {len(rows)} item(s)" if rows else "empty result"
    results.append(_row(provider_id, check, status, message, count=len(rows), key_mask=key_mask))


def _status_from_error(error: ProviderError) -> str:
    if error.state in FAIL_STATES:
        return "failed"
    if error.state in WARN_STATES:
        return "warning"
    return "failed"


def _row(
    provider: str,
    check: str,
    status: str,
    message: str,
    *,
    count: int = 0,
    error_state: str = "",
    key_mask: str = "",
) -> dict[str, Any]:
    return {
        "provider": provider,
        "check": check,
        "status": status,
        "message": _redact(message),
        "count": count,
        "error_state": error_state,
        "key_mask": key_mask,
    }


def _summary(results: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "passed": sum(1 for item in results if item["status"] == "passed"),
        "warning": sum(1 for item in results if item["status"] == "warning"),
        "failed": sum(1 for item in results if item["status"] == "failed"),
        "skipped": sum(1 for item in results if item["status"] == "skipped"),
    }


def _print_report(report: dict[str, Any]) -> None:
    print("Real provider smoke test")
    for item in report["results"]:
        print(f"- {item['provider']} | {item['check']} | {item['status']} | {item['message']} | key={item['key_mask']}")
    print(f"Summary: {report['summary']}")
    print(f"Report: {REPORT_PATH}")


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _redact(value: str) -> str:
    for key in ("FMP_API_KEY", "ALPHA_VANTAGE_API_KEY", "MARKETAUX_API_KEY"):
        secret = os.environ.get(key)
        if secret:
            value = value.replace(secret, "***")
    return value.replace("apikey=", "apikey=***").replace("api_token=", "api_token=***")


if __name__ == "__main__":
    sys.exit(main())
