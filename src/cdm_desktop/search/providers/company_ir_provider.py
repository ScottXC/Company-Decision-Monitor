from __future__ import annotations

from datetime import UTC, datetime

import httpx
from bs4 import BeautifulSoup

from cdm_desktop.search.models import (
    CompanySearchCandidate,
    ProviderRefreshResult,
    ProviderSearchResponse,
    SearchScope,
)
from cdm_desktop.search.ranking import score_candidate
from cdm_desktop.security.url_safety import validate_url


class CompanyIRProvider:
    provider_id = "company_ir"
    display_name = "Company IR"
    requires_api_key = False

    def __init__(self, urls: list[str] | None = None, *, timeout_seconds: int = 15) -> None:
        self.urls = urls or []
        self.timeout_seconds = timeout_seconds

    async def refresh_reference_data(self) -> ProviderRefreshResult:
        return ProviderRefreshResult(self.provider_id, "success", rows=len(self.urls), fetched_at=_now())

    async def search(self, query: str, scope: SearchScope, limit: int) -> ProviderSearchResponse:
        if scope not in {"all", "news", "filings"}:
            return ProviderSearchResponse(self.provider_id, "disabled", fetched_at=_now())
        if not self.urls:
            return ProviderSearchResponse(self.provider_id, "disabled", error_message="未配置公司 IR 页面。", fetched_at=_now())
        candidates = []
        errors = []
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True, trust_env=False) as client:
            for url in self.urls:
                try:
                    safe_url = validate_url(url)
                    response = await client.get(safe_url)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, "lxml")
                    text = soup.get_text(" ", strip=True)
                except Exception as exc:
                    errors.append(f"{url}: {exc}")
                    continue
                if query.lower() not in text.lower():
                    continue
                candidate = CompanySearchCandidate(
                    name=query,
                    market="新闻/网页",
                    source_provider=self.display_name,
                    source_url=url,
                    source_type="public_html",
                    match_reason="用户配置 IR 页面提及关键词",
                    freshness="user configured IR page",
                )
                candidates.append(score_candidate(candidate, query, scope, provider_id=self.provider_id))
                if len(candidates) >= limit:
                    break
        status = "partial" if errors and candidates else "failed" if errors else "success"
        return ProviderSearchResponse(self.provider_id, status, candidates, "; ".join(errors), fetched_at=_now())


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
