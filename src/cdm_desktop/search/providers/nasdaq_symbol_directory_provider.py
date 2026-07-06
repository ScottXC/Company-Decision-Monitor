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


class NasdaqSymbolDirectoryProvider:
    provider_id = "nasdaq_trader"
    display_name = "Nasdaq Trader"
    requires_api_key = False
    nasdaq_url = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
    other_url = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

    def __init__(
        self,
        *,
        timeout_seconds: int = 15,
        nasdaq_payload: str | None = None,
        other_payload: str | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.nasdaq_payload = nasdaq_payload
        self.other_payload = other_payload
        self._rows: list[dict[str, str]] | None = None

    async def refresh_reference_data(self) -> ProviderRefreshResult:
        try:
            rows = await self._load_rows(force=True)
        except Exception as exc:
            return ProviderRefreshResult(self.provider_id, "failed", error_message=str(exc), fetched_at=_now())
        return ProviderRefreshResult(self.provider_id, "success", rows=len(rows), fetched_at=_now())

    async def search(self, query: str, scope: SearchScope, limit: int) -> ProviderSearchResponse:
        if scope not in {"all", "us"}:
            return ProviderSearchResponse(self.provider_id, "disabled", [], fetched_at=_now())
        query = query.strip()
        if not query:
            return ProviderSearchResponse(self.provider_id, "success", [], fetched_at=_now())
        try:
            rows = await self._load_rows()
        except Exception as exc:
            return ProviderSearchResponse(self.provider_id, "failed", [], str(exc), fetched_at=_now())

        normalized = query.lower()
        candidates = []
        for row in rows:
            symbol = row["symbol"].upper()
            name = row["name"]
            if normalized != symbol.lower() and normalized not in name.lower():
                continue
            candidate = CompanySearchCandidate(
                name=name,
                legal_name=name,
                ticker=symbol,
                exchange=row.get("exchange", "NASDAQ"),
                market="美股",
                country="美国",
                source_provider=self.display_name,
                source_url=row.get("source_url", self.nasdaq_url),
                source_type="public_txt",
                match_reason="Nasdaq Trader Symbol Directory 匹配",
                freshness="Nasdaq Trader symbol directory",
                raw_payload_json=orjson.dumps(row).decode("utf-8"),
                contributing_providers=(self.display_name,),
            )
            candidates.append(score_candidate(candidate, query, scope, provider_id=self.provider_id))
            if len(candidates) >= limit:
                break
        return ProviderSearchResponse(self.provider_id, "success", candidates, fetched_at=_now())

    async def _load_rows(self, *, force: bool = False) -> list[dict[str, str]]:
        if self._rows is not None and not force:
            return self._rows
        nasdaq_text = self.nasdaq_payload
        other_text = self.other_payload
        if nasdaq_text is None or other_text is None:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True, trust_env=False) as client:
                if nasdaq_text is None:
                    nasdaq_text = (await client.get(self.nasdaq_url)).text
                if other_text is None:
                    other_text = (await client.get(self.other_url)).text
        self._rows = [
            *_parse_nasdaq_listed(nasdaq_text, self.nasdaq_url),
            *_parse_other_listed(other_text, self.other_url),
        ]
        return self._rows


def _parse_nasdaq_listed(text: str, source_url: str) -> list[dict[str, str]]:
    rows = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[1:]:
        if line.startswith("File Creation Time"):
            continue
        parts = line.split("|")
        if len(parts) < 8 or parts[3].upper() == "Y":
            continue
        rows.append(
            {
                "symbol": parts[0],
                "name": parts[1],
                "exchange": "NASDAQ",
                "source_url": source_url,
            }
        )
    return rows


def _parse_other_listed(text: str, source_url: str) -> list[dict[str, str]]:
    rows = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[1:]:
        if line.startswith("File Creation Time"):
            continue
        parts = line.split("|")
        if len(parts) < 7 or parts[6].upper() == "Y":
            continue
        exchange = {"A": "NYSE American", "N": "NYSE", "P": "NYSE Arca", "Z": "BATS"}.get(parts[2], parts[2])
        rows.append(
            {
                "symbol": parts[0],
                "name": parts[1],
                "exchange": exchange,
                "source_url": source_url,
            }
        )
    return rows


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
