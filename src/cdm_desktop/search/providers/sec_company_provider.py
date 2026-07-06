from __future__ import annotations

from datetime import UTC, datetime

import httpx
import orjson

from cdm_desktop.search.models import (
    CompanySearchCandidate,
    ProviderRefreshResult,
    ProviderSearchResponse,
    SearchScope,
)
from cdm_desktop.search.ranking import score_candidate


class SECCompanyProvider:
    provider_id = "sec"
    display_name = "SEC"
    requires_api_key = False
    source_url = "https://www.sec.gov/files/company_tickers.json"

    def __init__(
        self,
        *,
        user_agent: str = "CompanyDecisionMonitor contact@example.com",
        timeout_seconds: int = 15,
        fixture_payload: bytes | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.fixture_payload = fixture_payload
        self._rows: list[dict[str, object]] | None = None

    async def refresh_reference_data(self) -> ProviderRefreshResult:
        try:
            rows = await self._load_rows(force=True)
        except Exception as exc:
            return ProviderRefreshResult(self.provider_id, "failed", error_message=str(exc), fetched_at=_now())
        return ProviderRefreshResult(self.provider_id, "success", rows=len(rows), fetched_at=_now())

    async def search(self, query: str, scope: SearchScope, limit: int) -> ProviderSearchResponse:
        if scope not in {"all", "us", "filings"}:
            return ProviderSearchResponse(self.provider_id, "disabled", [], fetched_at=_now())
        query = query.strip()
        if not query:
            return ProviderSearchResponse(self.provider_id, "success", [], fetched_at=_now())
        try:
            rows = await self._load_rows()
        except Exception as exc:
            return ProviderSearchResponse(self.provider_id, "failed", [], str(exc), fetched_at=_now())

        normalized = query.lower()
        candidates: list[CompanySearchCandidate] = []
        for row in rows:
            ticker = str(row.get("ticker") or "").upper()
            name = str(row.get("title") or "")
            cik = str(row.get("cik_str") or "")
            if not _matches(normalized, ticker, name, cik):
                continue
            candidate = CompanySearchCandidate(
                name=name,
                legal_name=name,
                ticker=ticker,
                exchange="SEC",
                market="美股",
                country="美国",
                source_provider=self.display_name,
                source_url=self.source_url,
                source_type="public_json",
                match_reason="SEC company_tickers 匹配",
                freshness="SEC company_tickers",
                raw_payload_json=orjson.dumps(row).decode("utf-8"),
                aliases=(cik,),
                contributing_providers=(self.display_name,),
            )
            candidates.append(score_candidate(candidate, query, scope, provider_id=self.provider_id))
            if len(candidates) >= limit:
                break
        return ProviderSearchResponse(self.provider_id, "success", candidates, fetched_at=_now())

    async def _load_rows(self, *, force: bool = False) -> list[dict[str, object]]:
        if self._rows is not None and not force:
            return self._rows
        if self.fixture_payload is not None:
            payload = self.fixture_payload
        else:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": self.user_agent},
                trust_env=False,
            ) as client:
                response = await client.get(self.source_url)
                response.raise_for_status()
                payload = response.content
        data = orjson.loads(payload)
        rows = list(data.values()) if isinstance(data, dict) else list(data)
        self._rows = [row for row in rows if isinstance(row, dict)]
        return self._rows


def _matches(query: str, ticker: str, name: str, cik: str) -> bool:
    return query == ticker.lower() or query in name.lower() or (query.isdigit() and query in cik)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
