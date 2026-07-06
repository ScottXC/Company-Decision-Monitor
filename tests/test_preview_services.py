from __future__ import annotations

import pytest

from cdm_desktop.services.preview_company_service import get_company_profile, get_financial_metrics
from cdm_desktop.services.preview_llm_service import summarize_company
from cdm_desktop.services.preview_news_service import get_company_news
from cdm_desktop.services.preview_search_service import search_companies
from cdm_desktop.services.preview_watchlist_service import list_watchlist


@pytest.mark.asyncio
async def test_preview_services_return_empty_state() -> None:
    assert await search_companies("keyword", "all") == []
    assert await get_company_profile("placeholder") is None
    assert await get_financial_metrics("placeholder") == []
    assert await get_company_news("placeholder") == []
    assert await list_watchlist() == []
    assert await summarize_company("placeholder") is None
