from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from io import StringIO
from typing import Any

from cdm_desktop.public_api.http_client import PublicHttpClient
from cdm_desktop.public_api.key_store import ApiKeyStore
from cdm_desktop.public_api.models import CompanyResult, NewsItem, ProviderError, ProviderMeta
from cdm_desktop.public_api.query import fuzzy_score


class PublicProvider(ABC):
    def __init__(
        self,
        meta: ProviderMeta,
        key_store: ApiKeyStore,
        http: PublicHttpClient,
    ) -> None:
        self.meta = meta
        self.key_store = key_store
        self.http = http

    def key(self) -> str:
        return self.key_store.get(self.meta.key_name) if self.meta.key_name else ""

    def missing_key_error(self) -> ProviderError:
        key_label = self.meta.key_name or "API key"
        return ProviderError(
            self.meta.provider_id,
            "not_configured",
            f"{self.meta.display_name} 未配置 {key_label}，该数据源已自动跳过。",
        )

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        raise NotImplementedError


class StubProvider(PublicProvider):
    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        if self.meta.requires_key and not self.key():
            return [], [], self.missing_key_error()
        return [], [], ProviderError(
            self.meta.provider_id,
            "disabled",
            f"{self.meta.display_name} 当前为 v0.1.1 stub：{self.meta.notes or '后续版本接入。'}",
        )


class FmpProvider(PublicProvider):
    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        key = self.key()
        if not key:
            return [], [], self.missing_key_error()
        data, error = self.http.get_json(
            self.meta.provider_id,
            "https://financialmodelingprep.com/api/v3/search",
            params={"query": query, "limit": limit, "apikey": key},
        )
        if error:
            return [], [], error
        companies = parse_fmp_search(data, query)
        news, news_error = self.news(query, limit=5)
        return companies, news, news_error if not companies and news_error else None

    def news(self, query: str, limit: int = 5) -> tuple[list[NewsItem], ProviderError | None]:
        key = self.key()
        if not key:
            return [], self.missing_key_error()
        data, error = self.http.get_json(
            self.meta.provider_id,
            "https://financialmodelingprep.com/api/v3/stock_news",
            params={"tickers": query, "limit": limit, "apikey": key},
        )
        if error:
            return [], error
        return parse_fmp_news(data), None


class AlphaVantageProvider(PublicProvider):
    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        key = self.key()
        if not key:
            return [], [], self.missing_key_error()
        data, error = self.http.get_json(
            self.meta.provider_id,
            "https://www.alphavantage.co/query",
            params={"function": "SYMBOL_SEARCH", "keywords": query, "apikey": key},
        )
        if error:
            return [], [], error
        if isinstance(data, dict) and ("Error Message" in data or "Information" in data):
            return [], [], ProviderError(
                self.meta.provider_id,
                "invalid_key",
                str(data.get("Error Message") or data.get("Information")),
            )
        return parse_alpha_symbol_search(data, query)[:limit], [], None


class MarketauxProvider(PublicProvider):
    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        key = self.key()
        if not key:
            return [], [], self.missing_key_error()
        data, error = self.http.get_json(
            self.meta.provider_id,
            "https://api.marketaux.com/v1/news/all",
            params={"search": query, "limit": limit, "api_token": key, "language": "en"},
        )
        if error:
            return [], [], error
        return [], parse_marketaux_news(data), None


class GleifProvider(PublicProvider):
    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        params = {"filter[fulltext]": query, "page[size]": limit}
        data, error = self.http.get_json(
            self.meta.provider_id,
            "https://api.gleif.org/api/v1/lei-records",
            params=params,
        )
        if error:
            return [], [], error
        return parse_gleif_records(data, query), [], None


class OpenCorporatesProvider(PublicProvider):
    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        key = self.key()
        if not key:
            return [], [], self.missing_key_error()
        data, error = self.http.get_json(
            self.meta.provider_id,
            "https://api.opencorporates.com/v0.4/companies/search",
            params={"q": query, "per_page": limit, "api_token": key},
        )
        if error:
            return [], [], error
        return parse_opencorporates(data, query), [], None


class CompaniesHouseProvider(PublicProvider):
    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        key = self.key()
        if not key:
            return [], [], self.missing_key_error()
        data, error = self.http.get_json(
            self.meta.provider_id,
            "https://api.company-information.service.gov.uk/search/companies",
            params={"q": query, "items_per_page": limit},
            auth=(key, ""),
        )
        if error:
            return [], [], error
        return parse_companies_house(data, query), [], None


class NorwayBrregProvider(PublicProvider):
    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        data, error = self.http.get_json(
            self.meta.provider_id,
            "https://data.brreg.no/enhetsregisteret/api/enheter",
            params={"navn": query, "size": limit},
        )
        if error:
            return [], [], error
        return parse_norway_brreg(data, query), [], None


class NasdaqDirectoryProvider(PublicProvider):
    url = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"

    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        text, error = self.http.get_text(self.meta.provider_id, self.url)
        if error:
            return [], [], error
        return parse_nasdaq_directory(text or "", query)[:limit], [], None


def provider_for(meta: ProviderMeta, key_store: ApiKeyStore, http: PublicHttpClient) -> PublicProvider:
    mapping: dict[str, type[PublicProvider]] = {
        "fmp": FmpProvider,
        "alpha_vantage": AlphaVantageProvider,
        "marketaux": MarketauxProvider,
        "gleif": GleifProvider,
        "opencorporates": OpenCorporatesProvider,
        "companies_house": CompaniesHouseProvider,
        "norway_brreg": NorwayBrregProvider,
        "nasdaq_directory": NasdaqDirectoryProvider,
    }
    return mapping.get(meta.provider_id, StubProvider)(meta, key_store, http)


def parse_fmp_search(data: Any, query: str) -> list[CompanyResult]:
    rows = data if isinstance(data, list) else []
    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "")
        symbol = str(row.get("symbol") or "")
        if not name and not symbol:
            continue
        results.append(
            CompanyResult(
                name=name or symbol,
                symbol=symbol,
                exchange=str(row.get("exchangeShortName") or row.get("stockExchange") or ""),
                market=str(row.get("exchangeShortName") or ""),
                provider="Financial Modeling Prep",
                provider_id="fmp",
                source_url="https://financialmodelingprep.com/",
                match_reason="FMP symbol/name search",
                match_score=max(fuzzy_score(query, name), fuzzy_score(query, symbol)),
                raw=row,
            )
        )
    return results


def parse_fmp_news(data: Any) -> list[NewsItem]:
    rows = data if isinstance(data, list) else []
    return [
        NewsItem(
            title=str(row.get("title") or ""),
            provider="Financial Modeling Prep",
            source=str(row.get("site") or ""),
            published_at=str(row.get("publishedDate") or ""),
            url=str(row.get("url") or ""),
            snippet=str(row.get("text") or "")[:240],
        )
        for row in rows
        if isinstance(row, dict) and row.get("title")
    ]


def parse_alpha_symbol_search(data: Any, query: str) -> list[CompanyResult]:
    rows = data.get("bestMatches", []) if isinstance(data, dict) else []
    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("1. symbol") or "")
        name = str(row.get("2. name") or "")
        results.append(
            CompanyResult(
                name=name or symbol,
                symbol=symbol,
                market=str(row.get("3. type") or ""),
                country=str(row.get("4. region") or ""),
                provider="Alpha Vantage",
                provider_id="alpha_vantage",
                source_url="https://www.alphavantage.co/",
                match_reason="Alpha Vantage SYMBOL_SEARCH",
                match_score=max(fuzzy_score(query, name), fuzzy_score(query, symbol)),
                raw=row,
            )
        )
    return results


def parse_marketaux_news(data: Any) -> list[NewsItem]:
    rows = data.get("data", []) if isinstance(data, dict) else []
    return [
        NewsItem(
            title=str(row.get("title") or ""),
            provider="Marketaux",
            source=str(row.get("source") or ""),
            published_at=str(row.get("published_at") or ""),
            url=str(row.get("url") or ""),
            snippet=str(row.get("description") or row.get("snippet") or "")[:240],
            language=str(row.get("language") or ""),
        )
        for row in rows
        if isinstance(row, dict) and row.get("title")
    ]


def parse_gleif_records(data: Any, query: str) -> list[CompanyResult]:
    rows = data.get("data", []) if isinstance(data, dict) else []
    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        attrs = row.get("attributes") or {}
        entity = attrs.get("entity") or {}
        legal_name = (entity.get("legalName") or {}).get("name") or ""
        jurisdiction = str(entity.get("jurisdiction") or "")
        country = str((entity.get("legalAddress") or {}).get("country") or "")
        lei = str(row.get("id") or attrs.get("lei") or "")
        results.append(
            CompanyResult(
                name=legal_name or lei,
                legal_name=legal_name,
                lei=lei,
                jurisdiction=jurisdiction,
                country=country,
                provider="GLEIF LEI",
                provider_id="gleif",
                source_url=f"https://search.gleif.org/#/record/{lei}" if lei else "https://search.gleif.org/",
                match_reason="GLEIF fulltext / LEI search",
                match_score=max(fuzzy_score(query, legal_name), fuzzy_score(query, lei)),
                raw=row,
            )
        )
    return results


def parse_opencorporates(data: Any, query: str) -> list[CompanyResult]:
    rows = (data.get("results") or {}).get("companies", []) if isinstance(data, dict) else []
    results = []
    for wrapper in rows:
        company = wrapper.get("company", {}) if isinstance(wrapper, dict) else {}
        name = str(company.get("name") or "")
        jurisdiction = str(company.get("jurisdiction_code") or "")
        number = str(company.get("company_number") or "")
        results.append(
            CompanyResult(
                name=name,
                company_number=number,
                jurisdiction=jurisdiction,
                provider="OpenCorporates",
                provider_id="opencorporates",
                source_url=str(company.get("opencorporates_url") or "https://opencorporates.com/"),
                match_reason="OpenCorporates company search",
                match_score=fuzzy_score(query, name),
                raw=company,
            )
        )
    return results


def parse_companies_house(data: Any, query: str) -> list[CompanyResult]:
    rows = data.get("items", []) if isinstance(data, dict) else []
    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("title") or "")
        number = str(row.get("company_number") or "")
        results.append(
            CompanyResult(
                name=name,
                company_number=number,
                jurisdiction="gb",
                country="United Kingdom",
                provider="UK Companies House",
                provider_id="companies_house",
                source_url=f"https://find-and-update.company-information.service.gov.uk/company/{number}",
                match_reason="Companies House name/company number search",
                match_score=fuzzy_score(query, name),
                raw=row,
            )
        )
    return results


def parse_norway_brreg(data: Any, query: str) -> list[CompanyResult]:
    embedded = data.get("_embedded", {}) if isinstance(data, dict) else {}
    rows = embedded.get("enheter", []) if isinstance(embedded, dict) else []
    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("navn") or "")
        number = str(row.get("organisasjonsnummer") or "")
        results.append(
            CompanyResult(
                name=name,
                company_number=number,
                jurisdiction="no",
                country="Norway",
                provider="Norway BRREG",
                provider_id="norway_brreg",
                source_url=f"https://data.brreg.no/enhetsregisteret/oppslag/enheter/{number}",
                match_reason="BRREG organization search",
                match_score=fuzzy_score(query, name),
                raw=row,
            )
        )
    return results


def parse_nasdaq_directory(text: str, query: str) -> list[CompanyResult]:
    rows = csv.DictReader(StringIO(text), delimiter="|")
    results = []
    for row in rows:
        symbol = str(row.get("Symbol") or "").strip()
        name = str(row.get("Security Name") or "").strip()
        if not symbol or symbol == "File Creation Time":
            continue
        score = max(fuzzy_score(query, symbol), fuzzy_score(query, name))
        if score < 60:
            continue
        results.append(
            CompanyResult(
                name=name or symbol,
                symbol=symbol,
                exchange="NASDAQ",
                market="US",
                country="United States",
                provider="Nasdaq Symbol Directory",
                provider_id="nasdaq_directory",
                source_url=NasdaqDirectoryProvider.url,
                match_reason="Nasdaq Trader public symbol directory",
                match_score=score,
                raw=dict(row),
            )
        )
    return sorted(results, key=lambda item: item.match_score, reverse=True)
