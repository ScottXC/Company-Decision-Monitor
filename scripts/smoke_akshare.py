from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cdm_desktop.paths import AppPaths  # noqa: E402
from cdm_desktop.public_api.cache import ApiCache  # noqa: E402
from cdm_desktop.public_api.http_client import PublicHttpClient  # noqa: E402
from cdm_desktop.public_api.key_store import ApiKeyStore  # noqa: E402
from cdm_desktop.public_api.models import CompanyResult  # noqa: E402
from cdm_desktop.public_api.providers import AkShareProvider  # noqa: E402
from cdm_desktop.public_api.registry import ProviderRegistry  # noqa: E402


def main() -> int:
    import akshare as ak

    report: dict[str, object] = {"version": ak.__version__, "results": [], "warnings": []}
    with tempfile.TemporaryDirectory(prefix="cdm-akshare-smoke-") as directory:
        root = Path(directory)
        paths = AppPaths(root, root / "logs", root / "raw", root / "exports", root / "cache", root / "cdm.db")
        meta = next(item for item in ProviderRegistry().all() if item.provider_id == "akshare")
        provider = AkShareProvider(meta, ApiKeyStore(paths), PublicHttpClient(timeout_seconds=5), ApiCache(paths))
        for company in (
            CompanyResult("贵州茅台", "中国及港股公开数据", "china_hk_symbol_index", symbol="SH600519", market="SH"),
            CompanyResult("腾讯控股", "中国及港股公开数据", "china_hk_symbol_index", symbol="HK00700", market="HK"),
        ):
            profile, error = provider.profile(company)
            item = {
                "symbol": company.symbol,
                "ok": profile is not None,
                "fields": sorted(profile.field_sources) if profile else [],
                "from_cache": bool(profile and profile.from_cache),
                "error": error.state if error else "",
                "message": error.message if error else "",
            }
            report["results"].append(item)  # type: ignore[union-attr]
            if error and error.state in {"provider_unavailable", "network_timeout"}:
                report["warnings"].append(f"{company.symbol}: upstream public source unavailable")  # type: ignore[union-attr]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    mapping_failures = [item for item in report["results"] if not item["ok"] and item["error"] not in {"provider_unavailable", "network_timeout"}]  # type: ignore[index,union-attr]
    return 1 if mapping_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
