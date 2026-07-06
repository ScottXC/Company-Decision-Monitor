from __future__ import annotations

import csv
import io
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


class StockConnectProvider:
    provider_id = "stock_connect"
    display_name = "HKEX Stock Connect"
    requires_api_key = False
    sse_url = "https://www.hkex.com.hk/-/media/HKEX-Market/Mutual-Market/Stock-Connect/Eligible-Stocks/SSE-Eligible-Stocks.csv"
    szse_url = "https://www.hkex.com.hk/-/media/HKEX-Market/Mutual-Market/Stock-Connect/Eligible-Stocks/SZSE-Eligible-Stocks.csv"
    coverage_note = "A股覆盖范围：沪深股通名单，不代表全部 A 股。"

    def __init__(
        self,
        *,
        timeout_seconds: int = 15,
        sse_payload: str | None = None,
        szse_payload: str | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.sse_payload = sse_payload
        self.szse_payload = szse_payload
        self._rows: list[dict[str, str]] | None = None

    async def refresh_reference_data(self) -> ProviderRefreshResult:
        try:
            rows = await self._load_rows(force=True)
        except Exception as exc:
            return ProviderRefreshResult(self.provider_id, "failed", error_message=str(exc), fetched_at=_now())
        return ProviderRefreshResult(self.provider_id, "success", rows=len(rows), fetched_at=_now())

    async def search(self, query: str, scope: SearchScope, limit: int) -> ProviderSearchResponse:
        if scope not in {"all", "a_share"}:
            return ProviderSearchResponse(self.provider_id, "disabled", [], fetched_at=_now())
        query = query.strip()
        if not query:
            return ProviderSearchResponse(self.provider_id, "success", [], fetched_at=_now())
        try:
            rows = await self._load_rows()
        except Exception as exc:
            return ProviderSearchResponse(self.provider_id, "partial", [], str(exc), fetched_at=_now())
        normalized = query.lower()
        candidates = []
        for row in rows:
            code = row["code"]
            name = row["name"]
            if normalized != code.lower() and normalized not in name.lower():
                continue
            candidate = CompanySearchCandidate(
                name=name,
                legal_name=name,
                ticker=code,
                exchange=row["exchange"],
                market="A股",
                country="中国",
                source_provider=self.display_name,
                source_url=row["source_url"],
                source_type="public_csv",
                match_reason="沪深股通名单匹配",
                freshness="HKEX Stock Connect eligible securities",
                raw_payload_json=orjson.dumps(row).decode("utf-8"),
                coverage_note=self.coverage_note,
                contributing_providers=(self.display_name,),
            )
            candidates.append(score_candidate(candidate, query, scope, provider_id=self.provider_id))
            if len(candidates) >= limit:
                break
        return ProviderSearchResponse(self.provider_id, "success", candidates, fetched_at=_now())

    async def _load_rows(self, *, force: bool = False) -> list[dict[str, str]]:
        if self._rows is not None and not force:
            return self._rows
        sse_text = self.sse_payload
        szse_text = self.szse_payload
        if sse_text is None or szse_text is None:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True, trust_env=False) as client:
                if sse_text is None:
                    sse_text = (await client.get(self.sse_url)).text
                if szse_text is None:
                    szse_text = (await client.get(self.szse_url)).text
        self._rows = [
            *_parse_stock_connect_csv(sse_text, "SSE", self.sse_url),
            *_parse_stock_connect_csv(szse_text, "SZSE", self.szse_url),
        ]
        return self._rows


def _parse_stock_connect_csv(text: str, exchange: str, source_url: str) -> list[dict[str, str]]:
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    for raw in reader:
        code = _first(raw, "Stock Code", "Code", "证券代码", "股票代码")
        name = _first(raw, "Stock Name", "Name", "Security Name", "证券名称", "股票简称")
        if code and name:
            rows.append({"code": code.strip(), "name": name.strip(), "exchange": exchange, "source_url": source_url})
    return rows


def _first(row: dict[str, str], *names: str) -> str:
    lowered = {str(key).strip().lower(): str(value).strip() for key, value in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value:
            return value
    return ""


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
