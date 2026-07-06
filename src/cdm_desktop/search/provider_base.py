from __future__ import annotations

from typing import Protocol

from cdm_desktop.search.models import ProviderRefreshResult, ProviderSearchResponse, SearchScope


class OnlineCompanySearchProvider(Protocol):
    provider_id: str
    display_name: str
    requires_api_key: bool

    async def search(self, query: str, scope: SearchScope, limit: int) -> ProviderSearchResponse:
        ...

    async def refresh_reference_data(self) -> ProviderRefreshResult:
        ...
