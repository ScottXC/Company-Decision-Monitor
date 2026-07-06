from __future__ import annotations

from datetime import UTC, datetime

from cdm_desktop.search.models import ProviderRefreshResult, ProviderSearchResponse, SearchScope


class HKEXNewsProvider:
    provider_id = "hkexnews"
    display_name = "HKEXnews"
    requires_api_key = False

    async def refresh_reference_data(self) -> ProviderRefreshResult:
        return ProviderRefreshResult(
            self.provider_id,
            "disabled",
            error_message="HKEXnews 页面结构可能变化，v1 默认不进行主动抓取。",
            fetched_at=_now(),
        )

    async def search(self, query: str, scope: SearchScope, limit: int) -> ProviderSearchResponse:
        if scope not in {"all", "hk", "filings"}:
            return ProviderSearchResponse(self.provider_id, "disabled", fetched_at=_now())
        return ProviderSearchResponse(
            self.provider_id,
            "disabled",
            error_message="HKEXnews 保守模式：请通过设置添加具体 HKEXnews/RSS 来源进行监控。",
            fetched_at=_now(),
        )


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
