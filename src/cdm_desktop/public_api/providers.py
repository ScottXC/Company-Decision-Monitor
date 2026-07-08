from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from datetime import datetime
from io import StringIO
from typing import Any

from cdm_desktop.public_api.cache import ApiCache, cache_key
from cdm_desktop.public_api.http_client import PublicHttpClient
from cdm_desktop.public_api.key_store import ApiKeyStore
from cdm_desktop.public_api.models import (
    CompanyProfile,
    CompanyResult,
    NewsItem,
    ProviderError,
    ProviderMeta,
)
from cdm_desktop.public_api.query import fuzzy_score
from cdm_desktop.public_api.xueqiu_external_link import build_xueqiu_external_link

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
NASDAQ_OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"


class PublicProvider(ABC):
    def __init__(
        self,
        meta: ProviderMeta,
        key_store: ApiKeyStore,
        http: PublicHttpClient,
        cache: ApiCache | None = None,
    ) -> None:
        self.meta = meta
        self.key_store = key_store
        self.http = http
        self.cache = cache

    def key(self) -> str:
        return self.key_store.get(self.meta.key_name) if self.meta.key_name else ""

    def missing_key_error(self) -> ProviderError:
        key_label = self.meta.key_name or "API key"
        return ProviderError(
            self.meta.provider_id,
            "not_configured",
            f"{self.meta.display_name} is not configured: {key_label}. This provider was skipped.",
        )

    def test_connection(self) -> ProviderError | None:
        _companies, _news, error = self.search("Apple", limit=1)
        return error

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        raise NotImplementedError

    def profile(self, company: CompanyResult) -> tuple[CompanyProfile | None, ProviderError | None]:
        return None, ProviderError(
            self.meta.provider_id,
            "disabled",
            f"{self.meta.display_name} does not provide company profile data in this version.",
        )

    def news(self, *, symbol: str = "", company_name: str = "", limit: int = 20) -> tuple[list[NewsItem], ProviderError | None]:
        return [], ProviderError(
            self.meta.provider_id,
            "disabled",
            f"{self.meta.display_name} does not provide news data in this version.",
        )


class StubProvider(PublicProvider):
    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        if self.meta.requires_key and not self.key():
            return [], [], self.missing_key_error()
        note = self.meta.notes or "Future version provider."
        return [], [], ProviderError(self.meta.provider_id, "disabled", f"{self.meta.display_name} is a stub: {note}")


class XueqiuExternalLinkProvider(PublicProvider):
    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        _ = (query, limit)
        return [], [], None

    def build_link(self, company: CompanyResult):
        return build_xueqiu_external_link(
            symbol=company.symbol,
            exchange=company.exchange,
            market=company.market,
            company_name=company.name or company.display_name or company.legal_name,
        )


class FmpProvider(PublicProvider):
    def test_connection(self) -> ProviderError | None:
        key = self.key()
        if not key:
            return self.missing_key_error()
        data, error = self.http.get_json(
            self.meta.provider_id,
            "https://financialmodelingprep.com/api/v3/search",
            params={"query": "AAPL", "limit": 1, "apikey": key},
        )
        return _fmp_payload_error(data, self.meta.provider_id) or error

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
        payload_error = _fmp_payload_error(data, self.meta.provider_id)
        if payload_error:
            return [], [], payload_error
        companies = parse_fmp_search(data, query)
        return companies, [], None if companies else ProviderError(self.meta.provider_id, "empty", "FMP returned no company results.")

    def profile(self, company: CompanyResult) -> tuple[CompanyProfile | None, ProviderError | None]:
        key = self.key()
        symbol = company.symbol.strip()
        if not key:
            return None, self.missing_key_error()
        if not symbol:
            return None, ProviderError(self.meta.provider_id, "empty", "FMP profile requires a symbol.")
        data, error = self.http.get_json(
            self.meta.provider_id,
            "https://financialmodelingprep.com/stable/profile",
            params={"symbol": symbol, "apikey": key},
        )
        if error:
            data, error = self.http.get_json(
                self.meta.provider_id,
                f"https://financialmodelingprep.com/api/v3/profile/{symbol}",
                params={"apikey": key},
            )
        if error:
            return None, error
        payload_error = _fmp_payload_error(data, self.meta.provider_id)
        if payload_error:
            return None, payload_error
        profile = parse_fmp_profile(data)
        if not profile:
            return None, ProviderError(self.meta.provider_id, "empty", "FMP profile returned no data.")
        return profile, None

    def news(self, *, symbol: str = "", company_name: str = "", limit: int = 20) -> tuple[list[NewsItem], ProviderError | None]:
        key = self.key()
        if not key:
            return [], self.missing_key_error()
        query_symbol = symbol.strip()
        if not query_symbol and not company_name.strip():
            return [], ProviderError(self.meta.provider_id, "empty", "FMP news requires a symbol or company name.")
        params: dict[str, Any] = {"limit": limit, "apikey": key}
        if query_symbol:
            params["tickers"] = query_symbol
        data, error = self.http.get_json(
            self.meta.provider_id,
            "https://financialmodelingprep.com/api/v3/stock_news",
            params=params,
        )
        if error:
            return [], error
        payload_error = _fmp_payload_error(data, self.meta.provider_id)
        if payload_error:
            return [], payload_error
        news = parse_fmp_news(data, query=company_name or symbol)
        return news[:limit], None if news else ProviderError(self.meta.provider_id, "empty", "FMP news returned no data.")


class AlphaVantageProvider(PublicProvider):
    def test_connection(self) -> ProviderError | None:
        key = self.key()
        if not key:
            return self.missing_key_error()
        data, error = self.http.get_json(
            self.meta.provider_id,
            "https://www.alphavantage.co/query",
            params={"function": "SYMBOL_SEARCH", "keywords": "IBM", "apikey": key},
        )
        return _alpha_payload_error(data, self.meta.provider_id) or error

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
        payload_error = _alpha_payload_error(data, self.meta.provider_id)
        if payload_error:
            return [], [], payload_error
        results = parse_alpha_symbol_search(data, query)[:limit]
        return results, [], None if results else ProviderError(self.meta.provider_id, "empty", "Alpha Vantage returned no company results.")

    def profile(self, company: CompanyResult) -> tuple[CompanyProfile | None, ProviderError | None]:
        key = self.key()
        symbol = company.symbol.strip()
        if not key:
            return None, self.missing_key_error()
        if not symbol:
            return None, ProviderError(self.meta.provider_id, "empty", "Alpha Vantage OVERVIEW requires a symbol.")
        data, error = self.http.get_json(
            self.meta.provider_id,
            "https://www.alphavantage.co/query",
            params={"function": "OVERVIEW", "symbol": symbol, "apikey": key},
        )
        if error:
            return None, error
        payload_error = _alpha_payload_error(data, self.meta.provider_id)
        if payload_error:
            return None, payload_error
        profile = parse_alpha_overview(data)
        if not profile:
            return None, ProviderError(self.meta.provider_id, "empty", "Alpha Vantage OVERVIEW returned no data.")
        return profile, None


class MarketauxProvider(PublicProvider):
    def test_connection(self) -> ProviderError | None:
        news, error = self.news(symbol="AAPL", limit=1)
        return error if not news else None

    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        news, error = self.news(company_name=query, limit=limit)
        return [], news, error

    def news(self, *, symbol: str = "", company_name: str = "", limit: int = 20) -> tuple[list[NewsItem], ProviderError | None]:
        key = self.key()
        if not key:
            return [], self.missing_key_error()
        params: dict[str, Any] = {
            "limit": limit,
            "api_token": key,
            "language": "en",
            "sort": "published_desc",
        }
        if symbol:
            params["symbols"] = symbol
        elif company_name:
            params["search"] = company_name
        else:
            return [], ProviderError(self.meta.provider_id, "empty", "Marketaux requires a symbol or company name.")
        data, error = self.http.get_json(
            self.meta.provider_id,
            "https://api.marketaux.com/v1/news/all",
            params=params,
        )
        if error:
            return [], error
        payload_error = _marketaux_payload_error(data, self.meta.provider_id)
        if payload_error:
            return [], payload_error
        news = parse_marketaux_news(data)
        return news[:limit], None if news else ProviderError(self.meta.provider_id, "empty", "Marketaux returned no news.")


class GleifProvider(PublicProvider):
    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        params = {"page[size]": limit}
        if _looks_like_lei(query):
            params["filter[lei]"] = query.strip().upper()
        else:
            params["filter[fulltext]"] = query
        data, error = self.http.get_json(
            self.meta.provider_id,
            "https://api.gleif.org/api/v1/lei-records",
            params=params,
        )
        if error:
            return [], [], error
        results = parse_gleif_records(data, query)
        return results, [], None if results else ProviderError(self.meta.provider_id, "empty", "GLEIF returned no results.")

    def profile(self, company: CompanyResult) -> tuple[CompanyProfile | None, ProviderError | None]:
        if not company.lei:
            return None, ProviderError(self.meta.provider_id, "empty", "GLEIF profile requires LEI.")
        data, error = self.http.get_json(
            self.meta.provider_id,
            f"https://api.gleif.org/api/v1/lei-records/{company.lei}",
        )
        if error:
            return None, error
        results = parse_gleif_records({"data": [data.get("data")]} if isinstance(data, dict) else data, company.lei)
        if not results:
            return None, ProviderError(self.meta.provider_id, "empty", "GLEIF profile returned no data.")
        result = results[0]
        return CompanyProfile(
            display_name=result.legal_name or result.name,
            lei=result.lei,
            country=result.country,
            provider_sources=["gleif"],
            field_sources={"display_name": "gleif", "lei": "gleif", "country": "gleif"},
            updated_at=_now(),
            raw=result.raw,
        ), None


class WikidataProvider(PublicProvider):
    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        data, error = self.http.get_json(
            self.meta.provider_id,
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbsearchentities",
                "format": "json",
                "language": "en",
                "type": "item",
                "search": query,
                "limit": limit,
            },
        )
        if error:
            return [], [], error
        results = parse_wikidata_search(data, query)
        return results, [], None if results else ProviderError(self.meta.provider_id, "empty", "No public encyclopedia entity information was found.")

    def profile(self, company: CompanyResult) -> tuple[CompanyProfile | None, ProviderError | None]:
        qid = company.wikidata_id.strip()
        if not qid:
            return None, ProviderError(self.meta.provider_id, "empty", "Wikidata profile requires QID.")
        data, error = self.http.get_json(
            self.meta.provider_id,
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbgetentities",
                "format": "json",
                "ids": qid,
                "props": "labels|descriptions|aliases|claims|sitelinks",
                "languages": "en|zh",
            },
        )
        if error:
            return None, error
        profile = parse_wikidata_profile(data, qid)
        if not profile:
            return None, ProviderError(self.meta.provider_id, "empty", "No public entity profile is available.")
        return profile, None


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
        results = parse_opencorporates(data, query)
        return results, [], None if results else ProviderError(self.meta.provider_id, "empty", "OpenCorporates returned no results.")


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
        results = parse_companies_house(data, query)
        return results, [], None if results else ProviderError(self.meta.provider_id, "empty", "Companies House returned no results.")


class NorwayBrregProvider(PublicProvider):
    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        data, error = self.http.get_json(
            self.meta.provider_id,
            "https://data.brreg.no/enhetsregisteret/api/enheter",
            params={"navn": query, "size": limit},
        )
        if error:
            return [], [], error
        results = parse_norway_brreg(data, query)
        return results, [], None if results else ProviderError(self.meta.provider_id, "empty", "BRREG returned no results.")


class NasdaqDirectoryProvider(PublicProvider):
    url = NASDAQ_LISTED_URL

    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        all_results: list[CompanyResult] = []
        errors: list[ProviderError] = []
        for url, source in [(NASDAQ_LISTED_URL, "nasdaqlisted"), (NASDAQ_OTHER_LISTED_URL, "otherlisted")]:
            text, error, from_cache = self._directory_text(url)
            if error and not text:
                errors.append(error)
                continue
            results = parse_nasdaq_directory(text or "", query, source=source)
            for result in results:
                result.from_cache = from_cache
            all_results.extend(results)
        sorted_results = sorted(_dedupe_company_results(all_results), key=lambda item: item.match_score, reverse=True)[:limit]
        if sorted_results:
            return sorted_results, [], errors[0] if len(errors) == 2 else None
        if errors:
            return [], [], errors[0]
        return [], [], ProviderError(self.meta.provider_id, "empty", "Nasdaq Symbol Directory returned no results.")

    def _directory_text(self, url: str) -> tuple[str | None, ProviderError | None, bool]:
        key = cache_key(self.meta.provider_id, url, {}, "")
        cached = self.cache.get(key) if self.cache else None
        if isinstance(cached, str):
            return cached, None, True
        text, error = self.http.get_text(self.meta.provider_id, url)
        if error:
            stale = self.cache.get_stale(key) if self.cache else None
            if isinstance(stale, str):
                return stale, error, True
            return None, error, False
        if self.cache and text:
            self.cache.set(key, text, ttl_seconds=86400)
        return text, None, False


def provider_for(
    meta: ProviderMeta,
    key_store: ApiKeyStore,
    http: PublicHttpClient,
    cache: ApiCache | None = None,
) -> PublicProvider:
    mapping: dict[str, type[PublicProvider]] = {
        "fmp": FmpProvider,
        "alpha_vantage": AlphaVantageProvider,
        "marketaux": MarketauxProvider,
        "gleif": GleifProvider,
        "wikidata": WikidataProvider,
        "opencorporates": OpenCorporatesProvider,
        "companies_house": CompaniesHouseProvider,
        "norway_brreg": NorwayBrregProvider,
        "nasdaq_directory": NasdaqDirectoryProvider,
        "xueqiu_external": XueqiuExternalLinkProvider,
    }
    return mapping.get(meta.provider_id, StubProvider)(meta, key_store, http, cache)


def parse_fmp_search(data: Any, query: str) -> list[CompanyResult]:
    rows = data if isinstance(data, list) else []
    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = _clean(row.get("name") or row.get("companyName"))
        symbol = _clean(row.get("symbol"))
        if not name and not symbol:
            continue
        exchange = _clean(row.get("exchangeShortName") or row.get("stockExchange") or row.get("exchange"))
        results.append(
            CompanyResult(
                name=name or symbol,
                display_name=name or symbol,
                symbol=symbol,
                exchange=exchange,
                market=exchange,
                category="financial",
                provider="Financial Modeling Prep",
                provider_id="fmp",
                source_url="https://financialmodelingprep.com/",
                match_reason="FMP symbol/name search",
                match_score=max(fuzzy_score(query, name), fuzzy_score(query, symbol)),
                updated_at=_now(),
                raw=row,
            )
        )
    return results


def parse_fmp_profile(data: Any) -> CompanyProfile | None:
    row = _first_row(data)
    if not row:
        return None
    profile = CompanyProfile(
        display_name=_clean(row.get("companyName") or row.get("name") or row.get("symbol")),
        symbol=_clean(row.get("symbol")),
        exchange=_clean(row.get("exchangeShortName") or row.get("exchange")),
        market=_clean(row.get("exchange") or row.get("stockExchangeName")),
        website=_clean(row.get("website")),
        description=_clean(row.get("description")),
        sector=_clean(row.get("sector")),
        industry=_clean(row.get("industry")),
        country=_clean(row.get("country")),
        price=_clean(row.get("price")),
        market_cap=_clean(row.get("mktCap") or row.get("marketCap")),
        currency=_clean(row.get("currency")),
        ceo=_clean(row.get("ceo")),
        employees=_clean(row.get("fullTimeEmployees")),
        phone=_clean(row.get("phone")),
        address=_clean(row.get("address")),
        city=_clean(row.get("city")),
        state=_clean(row.get("state")),
        zip_code=_clean(row.get("zip")),
        image_url=_clean(row.get("image")),
        ipo_date=_clean(row.get("ipoDate")),
        is_etf=_clean(row.get("isEtf")),
        is_actively_trading=_clean(row.get("isActivelyTrading")),
        is_adr=_clean(row.get("isAdr")),
        is_fund=_clean(row.get("isFund")),
        provider_sources=["fmp"],
        updated_at=_now(),
        raw={"fmp": row},
    )
    profile.field_sources = _field_sources(profile, "fmp")
    return profile


def parse_fmp_news(data: Any, query: str = "") -> list[NewsItem]:
    rows = data if isinstance(data, list) else []
    results = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("title"):
            continue
        results.append(
            NewsItem(
                id=_clean(row.get("symbol")) + ":" + _clean(row.get("publishedDate")),
                title=_clean(row.get("title")),
                provider="Financial Modeling Prep",
                provider_id="fmp",
                source=_clean(row.get("site") or row.get("publisher")),
                published_at=_clean(row.get("publishedDate") or row.get("date")),
                url=_clean(row.get("url")),
                snippet=_clean(row.get("text") or row.get("summary"))[:240],
                image_url=_clean(row.get("image")),
                entities=[{"query": query}] if query else [],
            )
        )
    return results


def parse_alpha_symbol_search(data: Any, query: str) -> list[CompanyResult]:
    rows = data.get("bestMatches", []) if isinstance(data, dict) else []
    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = _clean(row.get("1. symbol"))
        name = _clean(row.get("2. name"))
        results.append(
            CompanyResult(
                name=name or symbol,
                display_name=name or symbol,
                symbol=symbol,
                market=_clean(row.get("3. type")),
                country=_clean(row.get("4. region")),
                category="financial",
                provider="Alpha Vantage",
                provider_id="alpha_vantage",
                source_url="https://www.alphavantage.co/",
                match_reason="Alpha Vantage SYMBOL_SEARCH",
                match_score=_score_alpha_match(row, query, name, symbol),
                updated_at=_now(),
                raw=row,
            )
        )
    return results


def parse_alpha_overview(data: Any) -> CompanyProfile | None:
    if not isinstance(data, dict) or not _clean(data.get("Symbol") or data.get("Name")):
        return None
    profile = CompanyProfile(
        display_name=_clean(data.get("Name") or data.get("Symbol")),
        symbol=_clean(data.get("Symbol")),
        exchange=_clean(data.get("Exchange")),
        market=_clean(data.get("AssetType")),
        description=_clean(data.get("Description")),
        website=_clean(data.get("OfficialSite")),
        country=_clean(data.get("Country")),
        sector=_clean(data.get("Sector")),
        industry=_clean(data.get("Industry")),
        currency=_clean(data.get("Currency")),
        market_cap=_clean(data.get("MarketCapitalization")),
        provider_sources=["alpha_vantage"],
        updated_at=_now(),
        raw={"alpha_vantage": data},
    )
    if cik := _clean(data.get("CIK")):
        profile.raw["cik"] = cik
    for key in [
        "EBITDA", "PERatio", "PEGRatio", "BookValue", "DividendPerShare", "DividendYield", "EPS",
        "RevenueTTM", "GrossProfitTTM", "ProfitMargin", "OperatingMarginTTM", "ReturnOnAssetsTTM",
        "ReturnOnEquityTTM", "QuarterlyEarningsGrowthYOY", "QuarterlyRevenueGrowthYOY", "AnalystTargetPrice",
        "Beta", "52WeekHigh", "52WeekLow",
    ]:
        value = _clean(data.get(key))
        if value:
            profile.raw[key] = value
    profile.field_sources = _field_sources(profile, "alpha_vantage")
    return profile


def parse_marketaux_news(data: Any) -> list[NewsItem]:
    rows = data.get("data", []) if isinstance(data, dict) else []
    results = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("title"):
            continue
        source = row.get("source") or {}
        entities = row.get("entities") if isinstance(row.get("entities"), list) else []
        results.append(
            NewsItem(
                id=_clean(row.get("uuid") or row.get("id")),
                title=_clean(row.get("title")),
                provider="Marketaux",
                provider_id="marketaux",
                source=_clean(source.get("name") if isinstance(source, dict) else source),
                published_at=_clean(row.get("published_at")),
                url=_clean(row.get("url")),
                snippet=_clean(row.get("description") or row.get("snippet"))[:240],
                image_url=_clean(row.get("image_url") or row.get("image")),
                language=_clean(row.get("language")),
                country=_clean(row.get("country")),
                sentiment_score=_float_or_none(row.get("sentiment_score")),
                entities=[dict(item) for item in entities if isinstance(item, dict)],
            )
        )
    return results


def parse_gleif_records(data: Any, query: str) -> list[CompanyResult]:
    rows = data.get("data", []) if isinstance(data, dict) else []
    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        attrs = row.get("attributes") or {}
        entity = attrs.get("entity") or {}
        legal_name = _clean((entity.get("legalName") or {}).get("name"))
        jurisdiction = _clean(entity.get("jurisdiction"))
        legal_address = entity.get("legalAddress") or {}
        country = _clean(legal_address.get("country"))
        lei = _clean(row.get("id") or attrs.get("lei"))
        status = _clean((attrs.get("registration") or {}).get("status") or entity.get("status"))
        raw = dict(row)
        raw["registered_address"] = legal_address
        raw["status"] = status
        results.append(
            CompanyResult(
                name=legal_name or lei,
                display_name=legal_name or lei,
                legal_name=legal_name,
                lei=lei,
                jurisdiction=jurisdiction,
                country=country,
                category="global",
                provider="GLEIF LEI",
                provider_id="gleif",
                source_url=f"https://search.gleif.org/#/record/{lei}" if lei else "https://search.gleif.org/",
                match_reason="GLEIF fulltext / LEI search",
                match_score=max(fuzzy_score(query, legal_name), fuzzy_score(query, lei)),
                updated_at=_now(),
                raw=raw,
            )
        )
    return results


def parse_wikidata_search(data: Any, query: str) -> list[CompanyResult]:
    rows = data.get("search", []) if isinstance(data, dict) else []
    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        qid = _clean(row.get("id"))
        label = _clean(row.get("label"))
        aliases = [_clean(item) for item in row.get("aliases", []) if item]
        results.append(
            CompanyResult(
                name=label or qid,
                display_name=label or qid,
                wikidata_id=qid,
                description=_clean(row.get("description")),
                aliases=aliases,
                category="global",
                provider="Wikidata / Wikipedia",
                provider_id="wikidata",
                source_url=f"https://www.wikidata.org/wiki/{qid}" if qid else "https://www.wikidata.org/",
                match_reason="Wikidata entity search",
                match_score=max([fuzzy_score(query, label), *[fuzzy_score(query, alias) for alias in aliases]]),
                updated_at=_now(),
                raw=row,
            )
        )
    return results


def parse_wikidata_profile(data: Any, qid: str) -> CompanyProfile | None:
    entity = (data.get("entities") or {}).get(qid) if isinstance(data, dict) else None
    if not isinstance(entity, dict):
        return None
    labels = entity.get("labels") or {}
    descriptions = entity.get("descriptions") or {}
    sitelinks = entity.get("sitelinks") or {}
    label = _language_value(labels, "en") or _language_value(labels, "zh") or qid
    description = _language_value(descriptions, "en") or _language_value(descriptions, "zh")
    title = ((sitelinks.get("enwiki") or {}).get("title") or (sitelinks.get("zhwiki") or {}).get("title") or "")
    wikipedia_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}" if title else ""
    profile = CompanyProfile(
        display_name=label,
        wikidata_id=qid,
        wikipedia_url=wikipedia_url,
        description=description,
        provider_sources=["wikidata"],
        updated_at=_now(),
        raw={"wikidata": entity},
    )
    profile.field_sources = _field_sources(profile, "wikidata")
    return profile


def parse_opencorporates(data: Any, query: str) -> list[CompanyResult]:
    rows = (((data or {}).get("results") or {}).get("companies") or []) if isinstance(data, dict) else []
    results = []
    for wrapper in rows:
        row = wrapper.get("company") if isinstance(wrapper, dict) else None
        if not isinstance(row, dict):
            continue
        name = _clean(row.get("name"))
        jurisdiction = _clean(row.get("jurisdiction_code"))
        number = _clean(row.get("company_number"))
        results.append(
            CompanyResult(
                name=name,
                display_name=name,
                company_number=number,
                jurisdiction=jurisdiction,
                category="registry",
                provider="OpenCorporates",
                provider_id="opencorporates",
                source_url=_clean(row.get("opencorporates_url")),
                match_reason="OpenCorporates company search",
                match_score=fuzzy_score(query, name),
                updated_at=_now(),
                raw=row,
            )
        )
    return results


def parse_companies_house(data: Any, query: str) -> list[CompanyResult]:
    rows = data.get("items", []) if isinstance(data, dict) else []
    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = _clean(row.get("title"))
        number = _clean(row.get("company_number"))
        results.append(
            CompanyResult(
                name=name,
                display_name=name,
                company_number=number,
                jurisdiction="uk",
                country="United Kingdom",
                category="registry",
                provider="UK Companies House",
                provider_id="companies_house",
                source_url=f"https://find-and-update.company-information.service.gov.uk/company/{number}",
                match_reason="Companies House company search",
                match_score=fuzzy_score(query, name),
                updated_at=_now(),
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
        name = _clean(row.get("navn"))
        number = _clean(row.get("organisasjonsnummer"))
        results.append(
            CompanyResult(
                name=name,
                display_name=name,
                company_number=number,
                jurisdiction="no",
                country="Norway",
                category="registry",
                provider="Norway BRREG",
                provider_id="norway_brreg",
                source_url=f"https://data.brreg.no/enhetsregisteret/oppslag/enheter/{number}",
                match_reason="BRREG organization search",
                match_score=fuzzy_score(query, name),
                updated_at=_now(),
                raw=row,
            )
        )
    return results


def parse_nasdaq_directory(text: str, query: str, *, source: str = "nasdaqlisted") -> list[CompanyResult]:
    rows = csv.DictReader(StringIO(text), delimiter="|")
    results = []
    for row in rows:
        symbol = _clean(row.get("Symbol") or row.get("ACT Symbol"))
        name = _clean(row.get("Security Name") or row.get("Security Name"))
        if not symbol or symbol == "File Creation Time":
            continue
        if _clean(row.get("Test Issue")).upper() == "Y":
            continue
        score = max(fuzzy_score(query, symbol), fuzzy_score(query, name))
        if score < 60:
            continue
        exchange = "NASDAQ" if source == "nasdaqlisted" else _exchange_from_otherlisted(row)
        is_etf = _clean(row.get("ETF")).upper() == "Y"
        results.append(
            CompanyResult(
                name=name or symbol,
                display_name=name or symbol,
                symbol=symbol,
                exchange=exchange,
                market="US",
                country="United States",
                category="financial",
                provider="Nasdaq Symbol Directory",
                provider_id="nasdaq_directory",
                source_url=NASDAQ_LISTED_URL if source == "nasdaqlisted" else NASDAQ_OTHER_LISTED_URL,
                match_reason="Nasdaq Trader public symbol directory",
                match_score=score,
                updated_at=_now(),
                raw={**dict(row), "is_etf": is_etf, "directory_source": source},
            )
        )
    return sorted(results, key=lambda item: item.match_score, reverse=True)


def _dedupe_company_results(companies: list[CompanyResult]) -> list[CompanyResult]:
    deduped: dict[str, CompanyResult] = {}
    for company in companies:
        existing = deduped.get(company.dedupe_key())
        if existing is None or company.match_score > existing.match_score:
            deduped[company.dedupe_key()] = company
    return list(deduped.values())


def _fmp_payload_error(data: Any, provider_id: str) -> ProviderError | None:
    if not isinstance(data, dict):
        return None
    text = str(
        data.get("Error Message")
        or data.get("error")
        or data.get("message")
        or data.get("Information")
        or ""
    )
    if not text:
        return None
    lowered = text.lower()
    if "limit" in lowered or "quota" in lowered:
        return ProviderError(
            provider_id,
            "quota_exceeded",
            "FMP free-tier quota may be exhausted. Please retry later.",
        )
    if "premium" in lowered or "upgrade" in lowered:
        return ProviderError(provider_id, "premium_endpoint", "This FMP endpoint may require premium access.")
    if "invalid" in lowered or "apikey" in lowered or "api key" in lowered:
        return ProviderError(provider_id, "invalid_key", "FMP API key may be invalid. Please check Settings.")
    return ProviderError(provider_id, "provider_unavailable", "FMP is temporarily unavailable. Other sources were still attempted.")


def _alpha_payload_error(data: Any, provider_id: str) -> ProviderError | None:
    if not isinstance(data, dict):
        return None
    text = str(data.get("Error Message") or data.get("Information") or data.get("Note") or "")
    if not text:
        return None
    lowered = text.lower()
    if "daily" in lowered or "limit" in lowered:
        return ProviderError(
            provider_id,
            "quota_exceeded",
            "Alpha Vantage daily free-tier limit may be reached. Please retry later.",
        )
    if "frequency" in lowered or "rate" in lowered or "standard api call frequency" in lowered:
        return ProviderError(provider_id, "rate_limited", "Alpha Vantage request frequency may be limited. Please retry later.")
    if "invalid" in lowered or "api key" in lowered:
        return ProviderError(provider_id, "invalid_key", "Alpha Vantage API key may be invalid. Please check Settings.")
    return ProviderError(
        provider_id,
        "provider_unavailable",
        "Alpha Vantage is temporarily unavailable. Other sources were still attempted.",
    )


def _marketaux_payload_error(data: Any, provider_id: str) -> ProviderError | None:
    if not isinstance(data, dict):
        return None
    error = data.get("error")
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    text = str(error or data.get("message") or meta.get("error") or "")
    if not text:
        return None
    lowered = text.lower()
    if "quota" in lowered or "limit" in lowered:
        return ProviderError(
            provider_id,
            "quota_exceeded",
            "Marketaux free-tier quota may be exhausted. Please retry later.",
        )
    if "token" in lowered or "invalid" in lowered or "api" in lowered:
        return ProviderError(provider_id, "invalid_key", "Marketaux API token may be invalid. Please check Settings.")
    if "rate" in lowered:
        return ProviderError(provider_id, "rate_limited", "Marketaux request frequency is limited. Please retry later.")
    return ProviderError(
        provider_id,
        "provider_unavailable",
        "Marketaux is temporarily unavailable. Other sources were still attempted.",
    )


def _score_alpha_match(row: dict[str, Any], query: str, name: str, symbol: str) -> int:
    raw_score = _float_or_none(row.get("9. matchScore"))
    if raw_score is not None:
        return int(raw_score * 100) if raw_score <= 1 else int(raw_score)
    return max(fuzzy_score(query, name), fuzzy_score(query, symbol))


def _exchange_from_otherlisted(row: dict[str, str]) -> str:
    code = _clean(row.get("Exchange")).upper()
    return {"A": "NYSE American", "N": "NYSE", "P": "NYSE Arca", "Z": "BATS", "V": "IEXG"}.get(
        code,
        code or "US",
    )


def _looks_like_lei(value: str) -> bool:
    cleaned = value.strip().upper()
    return len(cleaned) == 20 and cleaned.isalnum()


def _first_row(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                return item
    if isinstance(data, dict):
        return data
    return {}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"none", "null", "nan"}:
        return ""
    return text


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _language_value(data: dict[str, Any], language: str) -> str:
    item = data.get(language) or {}
    return _clean(item.get("value")) if isinstance(item, dict) else ""


def _field_sources(profile: CompanyProfile, provider_id: str) -> dict[str, str]:
    excluded = {"raw", "field_sources", "provider_sources", "from_cache"}
    return {
        field: provider_id
        for field, value in profile.to_dict().items()
        if value and field not in excluded
    }


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
