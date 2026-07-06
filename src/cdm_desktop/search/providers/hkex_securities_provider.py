from __future__ import annotations

import csv
import io
import zipfile
from datetime import UTC, datetime
from xml.etree import ElementTree

import httpx
import orjson

from cdm_desktop.search.models import (
    CompanySearchCandidate,
    ProviderRefreshResult,
    ProviderSearchResponse,
    SearchScope,
)
from cdm_desktop.search.ranking import score_candidate


class HKEXSecuritiesProvider:
    provider_id = "hkex"
    display_name = "HKEX"
    requires_api_key = False
    source_url = "https://www.hkex.com.hk/eng/services/trading/securities/securitieslists/ListOfSecurities.xlsx"

    def __init__(
        self,
        *,
        timeout_seconds: int = 15,
        fixture_bytes: bytes | None = None,
        fixture_text: str | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.fixture_bytes = fixture_bytes
        self.fixture_text = fixture_text
        self._rows: list[dict[str, str]] | None = None

    async def refresh_reference_data(self) -> ProviderRefreshResult:
        try:
            rows = await self._load_rows(force=True)
        except Exception as exc:
            return ProviderRefreshResult(self.provider_id, "failed", error_message=str(exc), fetched_at=_now())
        return ProviderRefreshResult(self.provider_id, "success", rows=len(rows), fetched_at=_now())

    async def search(self, query: str, scope: SearchScope, limit: int) -> ProviderSearchResponse:
        if scope not in {"all", "hk", "filings"}:
            return ProviderSearchResponse(self.provider_id, "disabled", [], fetched_at=_now())
        query = query.strip()
        if not query:
            return ProviderSearchResponse(self.provider_id, "success", [], fetched_at=_now())
        try:
            rows = await self._load_rows()
        except Exception as exc:
            return ProviderSearchResponse(self.provider_id, "failed", [], str(exc), fetched_at=_now())
        normalized = query.lower().lstrip("0")
        candidates = []
        for row in rows:
            code = row["code"]
            name = row["name"]
            if normalized not in {code.lower(), code.lstrip("0").lower()} and normalized not in name.lower():
                continue
            candidate = CompanySearchCandidate(
                name=name,
                legal_name=name,
                ticker=code,
                exchange="HKEX",
                market="港股",
                country="中国香港",
                source_provider=self.display_name,
                source_url=self.source_url,
                source_type="public_xlsx",
                match_reason="HKEX 证券列表匹配",
                freshness="HKEX securities list",
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
        if self.fixture_text is not None:
            rows = _parse_csv(self.fixture_text)
        else:
            payload = self.fixture_bytes
            if payload is None:
                async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True, trust_env=False) as client:
                    response = await client.get(self.source_url)
                    response.raise_for_status()
                    payload = response.content
            rows = _parse_xlsx(payload)
        self._rows = rows
        return rows


def _parse_csv(text: str) -> list[dict[str, str]]:
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    for raw in reader:
        code = _first(raw, "Stock Code", "Code", "证券代码", "股份代号")
        name = _first(raw, "Name", "Security Name", "Name of Securities", "股份名称")
        if code and name:
            rows.append({"code": code.zfill(5), "name": name})
    return rows


def _parse_xlsx(payload: bytes) -> list[dict[str, str]]:
    table = _xlsx_rows(payload)
    if not table:
        return []
    header_index = _find_header_index(table)
    headers = table[header_index]
    rows = []
    for values in table[header_index + 1 :]:
        raw = {headers[i]: values[i] if i < len(values) else "" for i in range(len(headers))}
        code = _first(raw, "Stock Code", "Code", "证券代码", "股份代号")
        name = _first(raw, "Name", "Security Name", "Name of Securities", "股份名称")
        if code and name:
            rows.append({"code": code.zfill(5), "name": name})
    return rows


def _xlsx_rows(payload: bytes) -> list[list[str]]:
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", ns):
                shared.append("".join(node.text or "" for node in item.findall(".//a:t", ns)))
        sheet_name = next(name for name in archive.namelist() if name.startswith("xl/worksheets/sheet"))
        root = ElementTree.fromstring(archive.read(sheet_name))
        rows = []
        for row in root.findall(".//a:row", ns):
            values = []
            for cell in row.findall("a:c", ns):
                value = cell.find("a:v", ns)
                text = value.text if value is not None and value.text is not None else ""
                if cell.get("t") == "s" and text:
                    text = shared[int(text)]
                values.append(text.strip())
            rows.append(values)
        return rows


def _find_header_index(rows: list[list[str]]) -> int:
    for index, row in enumerate(rows[:20]):
        joined = "|".join(row).lower()
        if "code" in joined or "stock" in joined or "股份" in joined:
            return index
    return 0


def _first(row: dict[str, str], *names: str) -> str:
    lowered = {str(key).strip().lower(): str(value).strip() for key, value in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value:
            return value
    return ""


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
