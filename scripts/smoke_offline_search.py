from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cdm_desktop.paths import AppPaths  # noqa: E402
from cdm_desktop.public_api.china_hk_index import CHINA_HK_INDEX_PATH  # noqa: E402
from cdm_desktop.public_api.models import ProviderError  # noqa: E402
from cdm_desktop.public_api.providers import SYMBOL_UNIVERSE_PATH  # noqa: E402
from cdm_desktop.public_api.search_service import PublicSearchService  # noqa: E402
from cdm_desktop.public_api.xueqiu_external_link import build_xueqiu_external_link  # noqa: E402


def main() -> int:
    cases = _offline_cases()
    with tempfile.TemporaryDirectory(prefix="cdm-offline-search-") as temp:
        service = PublicSearchService(_paths(Path(temp)))
        results: list[dict[str, Any]] = []
        for query, expected in cases:
            started = time.perf_counter()
            response = service.search_local(query, use_cache=False, bypass_query_cache=True)
            elapsed_ms = (time.perf_counter() - started) * 1000
            symbols = {_comparable(item.symbol) for item in response.companies}
            results.append(
                {
                    "query": query,
                    "expected": expected,
                    "elapsed_ms": round(elapsed_ms, 3),
                    "found": _comparable(expected) in symbols,
                    "result_count": len(response.companies),
                    "news_count": len(response.news),
                }
            )

        base = service.search_local(cases[0][0], use_cache=False, bypass_query_cache=True)

        def offline_provider(*_args: Any, **_kwargs: Any) -> tuple[list[Any], ProviderError, float]:
            return [], ProviderError("offline", "network_timeout", "网络不可用，已保留本地结果。"), 0.1

        service._search_enrichment_provider = offline_provider  # type: ignore[method-assign]
        enriched = service.enrich_search(
            cases[0][0],
            base,
            use_cache=False,
            bypass_result_cache=True,
        )
        xueqiu = build_xueqiu_external_link(symbol="AAPL", company_name="Apple", market="US")
        report = {
            "version": "v0.1.4-generalized-search-performance-rc1",
            "mode": "simulated_offline_no_network_calls",
            "temporary_appdata": True,
            "cases": results,
            "local_p95_ms": _percentile([item["elapsed_ms"] for item in results], 0.95),
            "network_statuses": [status.state for status in enriched.statuses],
            "local_results_preserved": bool(enriched.companies),
            "ordinary_search_news_count": sum(item["news_count"] for item in results),
            "xueqiu_external_only": xueqiu.provider_type == "external_link" and xueqiu.open_mode == "system_browser",
        }
        report["passed"] = (
            all(item["found"] for item in results)
            and report["local_p95_ms"] <= 600
            and report["local_results_preserved"]
            and report["ordinary_search_news_count"] == 0
            and report["xueqiu_external_only"]
        )
    output = ROOT / "reports" / "offline_search_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


def _offline_cases() -> list[tuple[str, str]]:
    global_connection = sqlite3.connect(f"{SYMBOL_UNIVERSE_PATH.resolve().as_uri()}?mode=ro", uri=True)
    china_connection = sqlite3.connect(f"{CHINA_HK_INDEX_PATH.resolve().as_uri()}?mode=ro", uri=True)
    try:
        ticker, name = global_connection.execute(
            "SELECT normalized_symbol,name FROM symbols WHERE length(name)>8 "
            "ORDER BY ((id * 1103515245 + 7813) & 2147483647) LIMIT 1"
        ).fetchone()
        china_symbol, china_name = china_connection.execute(
            "SELECT normalized_symbol,chinese_name FROM symbols WHERE chinese_name!='' "
            "ORDER BY ((id * 1103515245 + 7813) & 2147483647) LIMIT 1"
        ).fetchone()
    finally:
        global_connection.close()
        china_connection.close()
    return [(str(ticker), str(ticker)), (str(name), str(ticker)), (str(china_name), str(china_symbol)), ("Apple", "AAPL")]


def _paths(root: Path) -> AppPaths:
    return AppPaths(root, root / "logs", root / "raw", root / "exports", root / "cache", root / "cdm.db").ensure()


def _comparable(value: str) -> str:
    symbol = value.strip().upper().replace("-", ".")
    if symbol.endswith(".SS"):
        return "SH" + symbol.split(".", 1)[0]
    if symbol.endswith(".SZ"):
        return "SZ" + symbol.split(".", 1)[0]
    if symbol.endswith(".HK"):
        return "HK" + symbol.split(".", 1)[0].zfill(5)
    return symbol


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction)))
    return round(float(ordered[index]), 3)


if __name__ == "__main__":
    raise SystemExit(main())
