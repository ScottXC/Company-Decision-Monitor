from __future__ import annotations

from cdm_desktop.types import CompanyProfile, SearchScope


async def search_companies(keyword: str, scope: SearchScope = "all") -> list[CompanyProfile]:
    """Future extension point for company search data sources.

    UI Preview Mode intentionally returns no results and performs no network call.
    """

    _ = (keyword, scope)
    return []
