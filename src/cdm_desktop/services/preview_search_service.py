from __future__ import annotations

from cdm_desktop.types import CompanyProfile, SearchScope


async def search_companies(keyword: str, scope: SearchScope = "all") -> list[CompanyProfile]:
    """Future extension point for company search data sources.

    Compatibility placeholder. Real company search lives in cdm_desktop.public_api.
    """

    _ = (keyword, scope)
    return []
