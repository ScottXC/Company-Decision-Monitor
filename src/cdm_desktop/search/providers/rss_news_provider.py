from __future__ import annotations

from datetime import UTC, datetime

import feedparser
import httpx

from cdm_desktop.search.models import (
    CompanySearchCandidate,
    ProviderRefreshResult,
    ProviderSearchResponse,
    SearchScope,
)
from cdm_desktop.search.ranking import score_candidate


class RSSNewsProvider:
    provider_id = "rss_news"
    display_name = "RSS/news"
    requires_api_key = False

    def __init__(self, feed_urls: list[str] | None = None, *, timeout_seconds: int = 15) -> None:
        self.feed_urls = feed_urls or []
        self.timeout_seconds = timeout_seconds

    async def refresh_reference_data(self) -> ProviderRefreshResult:
        return ProviderRefreshResult(self.provider_id, "success", rows=len(self.feed_urls), fetched_at=_now())

    async def search(self, query: str, scope: SearchScope, limit: int) -> ProviderSearchResponse:
        if scope not in {"all", "news"}:
            return ProviderSearchResponse(self.provider_id, "disabled", fetched_at=_now())
        if not self.feed_urls:
            return ProviderSearchResponse(
                self.provider_id,
                "disabled",
                error_message="未配置 RSS 新闻源。",
                fetched_at=_now(),
            )
        query = query.strip()
        if not query:
            return ProviderSearchResponse(self.provider_id, "success", [], fetched_at=_now())
        candidates: list[CompanySearchCandidate] = []
        errors = []
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True, trust_env=False) as client:
            for url in self.feed_urls:
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    feed = feedparser.parse(response.content)
                except Exception as exc:
                    errors.append(f"{url}: {exc}")
                    continue
                for entry in feed.entries:
                    title = str(getattr(entry, "title", ""))
                    summary = str(getattr(entry, "summary", ""))
                    text = f"{title} {summary}"
                    if query.lower() not in text.lower():
                        continue
                    candidate = CompanySearchCandidate(
                        name=query,
                        market="新闻/网页",
                        source_provider=self.display_name,
                        source_url=str(getattr(entry, "link", url)),
                        source_type="rss",
                        match_reason="用户配置 RSS 提及关键词",
                        freshness="RSS feed",
                    )
                    candidates.append(score_candidate(candidate, query, scope, provider_id=self.provider_id))
                    if len(candidates) >= limit:
                        break
        status = "partial" if errors and candidates else "failed" if errors else "success"
        return ProviderSearchResponse(self.provider_id, status, candidates, "; ".join(errors), fetched_at=_now())


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
