from __future__ import annotations

from cdm_desktop.types import NewsItem


async def get_company_news(company_id: str | None = None) -> list[NewsItem]:
    """Future extension point for news, announcements, RSS, and filings."""

    _ = company_id
    return []
