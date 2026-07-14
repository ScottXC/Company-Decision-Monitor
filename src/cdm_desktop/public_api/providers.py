from __future__ import annotations

import csv
import json
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import feedparser

from cdm_desktop.public_api.cache import ApiCache, cache_key
from cdm_desktop.public_api.china_hk_index import (
    CHINA_HK_INDEX_PATH,
    index_metadata,
    normalize_china_hk_symbol,
)
from cdm_desktop.public_api.http_client import PublicHttpClient
from cdm_desktop.public_api.key_store import ApiKeyStore
from cdm_desktop.public_api.models import (
    CompanyProfile,
    CompanyResult,
    NewsItem,
    ProviderError,
    ProviderMeta,
)
from cdm_desktop.public_api.provider_health import utc_timestamp
from cdm_desktop.public_api.query import (
    fuzzy_score,
    normalize_cn_symbol,
    normalize_hk_symbol,
    remove_company_suffix,
    shortlist_fuzzy_score,
)
from cdm_desktop.public_api.search_index_manager import SearchIndexManager
from cdm_desktop.public_api.search_query_plan import build_search_query_plan
from cdm_desktop.public_api.seed_aliases import expand_query_aliases, seed_alias_exact_match
from cdm_desktop.public_api.xueqiu_external_link import build_xueqiu_external_link

NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
NASDAQ_OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
SYMBOL_UNIVERSE_PATH = Path(__file__).resolve().parents[1] / "resources" / "symbol_universe" / "symbol_universe.sqlite"


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


class RssNewsProvider(PublicProvider):
    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        news, error = self.news(company_name=query, limit=limit)
        return [], news, error

    def news(self, *, symbol: str = "", company_name: str = "", limit: int = 20) -> tuple[list[NewsItem], ProviderError | None]:
        query = (company_name or symbol).strip()
        if not query:
            return [], ProviderError(self.meta.provider_id, "empty", "RSS news requires a query.")
        rows: list[NewsItem] = []
        errors: list[ProviderError] = []
        for provider_name, url in _rss_search_urls(query):
            text, error = self.http.get_text(self.meta.provider_id, url)
            if error:
                errors.append(error)
                continue
            rows.extend(parse_rss_news(text or "", query=query, provider_name=provider_name))
            if len(rows) >= limit:
                break
        if rows:
            return rows[:limit], None
        return [], errors[0] if errors else ProviderError(self.meta.provider_id, "empty", "RSS news returned no items.")


class SymbolUniverseProvider(PublicProvider):
    """Read the bundled FinanceDatabase-generated search index.

    The runtime app uses this compact SQLite index instead of importing the
    FinanceDatabase package. It is search metadata only, not realtime market data.
    """

    index_path = SYMBOL_UNIVERSE_PATH
    FUZZY_SHORTLIST_LIMIT = 100

    def __init__(
        self,
        meta: ProviderMeta,
        key_store: ApiKeyStore,
        http: PublicHttpClient,
        cache: ApiCache | None = None,
    ) -> None:
        super().__init__(meta, key_store, http, cache)
        self._exact_symbols: dict[str, list[dict[str, Any]]] | None = None
        self._exact_lock = threading.Lock()
        self._metadata: dict[str, Any] | None = None
        self.index_manager = SearchIndexManager.for_path(self.index_path)
        self.last_timing: dict[str, float | int] = {}

    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        if not self.index_path.exists():
            return [], [], ProviderError(
                self.meta.provider_id,
                "index_missing",
                "内置开源证券索引缺失，已跳过该搜索源。",
            )
        started = time.perf_counter()
        try:
            rows, metadata = self._query_index(query, min(max(limit * 5, 50), self.FUZZY_SHORTLIST_LIMIT))
        except sqlite3.DatabaseError:
            return [], [], ProviderError(
                self.meta.provider_id,
                "index_corrupted",
                "内置开源证券索引无法读取，可能已损坏。",
            )
        except OSError:
            return [], [], ProviderError(
                self.meta.provider_id,
                "provider_unavailable",
                "内置开源证券索引暂时不可用。",
            )
        query_ms = (time.perf_counter() - started) * 1000
        fuzzy_started = time.perf_counter()
        results = parse_symbol_universe_records(
            rows,
            query,
            provider_id=self.meta.provider_id,
            provider=self.meta.display_name,
            source_url="https://github.com/JerBouma/FinanceDatabase",
            generated_at=str(metadata.get("generated_at") or ""),
        )
        ranked = results[:limit]
        self.last_timing = {
            "sqlite_ms": query_ms,
            "fuzzy_ms": (time.perf_counter() - fuzzy_started) * 1000,
            "shortlist_size": len(rows),
        }
        return ranked, [], None if ranked else ProviderError(
            self.meta.provider_id,
            "empty",
            "内置开源证券索引没有返回匹配公司。",
        )

    def profile(self, company: CompanyResult) -> tuple[CompanyProfile | None, ProviderError | None]:
        if not company.symbol:
            return None, ProviderError(self.meta.provider_id, "empty", "内置开源证券索引详情需要 symbol。")
        if not self.index_path.exists():
            return None, ProviderError(self.meta.provider_id, "index_missing", "内置开源证券索引缺失。")
        raw = dict(company.raw or {})
        try:
            conn = self.index_manager.connection()
            row = conn.execute(
                "SELECT * FROM symbols WHERE normalized_symbol = ? LIMIT 1",
                (_normalize_symbol_for_index(company.symbol),),
            ).fetchone()
            if row:
                raw.update(dict(row))
        except sqlite3.DatabaseError:
            return None, ProviderError(self.meta.provider_id, "index_corrupted", "内置开源证券索引无法读取。")

        instrument_type = _clean(raw.get("instrument_type"))
        aliases = _symbol_universe_aliases(
            company.symbol,
            _clean(raw.get("name")) or company.name,
            _clean(raw.get("aliases_json")),
        )
        profile = CompanyProfile(
            id=_clean(raw.get("id")),
            display_name=_clean(raw.get("name")) or company.display_name or company.name,
            legal_name=_clean(raw.get("name")) or company.legal_name,
            aliases=aliases,
            symbol=_display_symbol_for_symbol_universe(_clean(raw.get("symbol")) or company.symbol),
            normalized_symbol=_normalize_symbol_for_index(_clean(raw.get("symbol")) or company.symbol),
            exchange=_clean(raw.get("exchange")) or company.exchange,
            market=_clean(raw.get("market")) or company.market,
            country=_clean(raw.get("country")) or company.country,
            sector=_clean(raw.get("sector")),
            industry=_clean(raw.get("industry")),
            currency=_clean(raw.get("currency")),
            instrument_type=instrument_type,
            is_listed=True,
            is_etf=instrument_type.casefold() == "etf",
            is_fund=instrument_type.casefold() == "fund",
            company_type="listed_company",
            official_source_url="https://github.com/JerBouma/FinanceDatabase",
            source_urls=["https://github.com/JerBouma/FinanceDatabase"],
            provider_sources=["symbol_universe"],
            updated_at=_clean(raw.get("index_generated_at")) or _now(),
            raw={
                **raw,
                "from_local_index": True,
                "source_note": "Bundled open-source symbol universe; not realtime market data.",
            },
        )
        profile.field_sources = _field_sources(profile, "symbol_universe")
        return profile, None

    def _query_index(self, query: str, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        terms = _symbol_universe_query_terms(query)
        plan = build_search_query_plan(query)
        rows_by_id: dict[int, dict[str, Any]] = {}
        conn = self.index_manager.connection()
        table = "symbols"
        metadata = self._load_metadata(conn)
        normalized_terms = _normalized_local_terms(terms)

        for term in terms:
            normalized_symbol = _normalize_symbol_for_index(term)
            for row in self._exact_symbol_rows(conn, table, normalized_symbol, limit):
                rows_by_id.setdefault(int(row["id"]), row)
        if rows_by_id and plan.query_type != "name":
            return list(rows_by_id.values())[:limit], metadata

        for term in normalized_terms[:12]:
            for row in conn.execute(
                "SELECT * FROM symbols WHERE normalized_name = ? LIMIT ?", (term, limit)
            ):
                rows_by_id.setdefault(int(row["id"]), dict(row))
            for row in conn.execute(
                "SELECT s.* FROM aliases a JOIN symbols s ON s.id=a.symbol_id "
                "WHERE a.normalized_alias=? LIMIT ?",
                (term, limit),
            ):
                rows_by_id.setdefault(int(row["id"]), dict(row))
        if rows_by_id:
            return list(rows_by_id.values())[:limit], metadata

        for term in normalized_terms[:4]:
            if len(term) < 2:
                continue
            upper = f"{term}\uffff"
            for row in conn.execute(
                "SELECT * FROM symbols WHERE normalized_name>=? AND normalized_name<? LIMIT ?",
                (term, upper, min(limit, 60)),
            ):
                rows_by_id.setdefault(int(row["id"]), dict(row))
            for row in conn.execute(
                "SELECT s.* FROM aliases a JOIN symbols s ON s.id=a.symbol_id "
                "WHERE a.normalized_alias>=? AND a.normalized_alias<? LIMIT ?",
                (term, upper, min(limit, 60)),
            ):
                rows_by_id.setdefault(int(row["id"]), dict(row))

        if len(rows_by_id) < limit and plan.allow_fuzzy:
            self._append_fts_shortlist(conn, table, list(plan.fts_terms), rows_by_id, limit)
        if len(rows_by_id) < limit and plan.ngrams and self.index_manager.has_object("name_ngrams"):
            _append_ngram_shortlist(conn, table, plan.ngrams, rows_by_id, limit)
        return list(rows_by_id.values())[:limit], metadata

    def _load_metadata(self, conn: sqlite3.Connection) -> dict[str, Any]:
        if self._metadata is not None:
            return self._metadata
        metadata: dict[str, Any] = {}
        for key, value in conn.execute("SELECT key, value FROM metadata"):
            try:
                metadata[str(key)] = json.loads(value)
            except (TypeError, json.JSONDecodeError):
                metadata[str(key)] = value
        self._metadata = metadata
        return metadata

    def _exact_symbol_rows(
        self,
        conn: sqlite3.Connection,
        table: str,
        normalized_symbol: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        if self._exact_symbols is None:
            self._exact_symbols = {}
        cached = self._exact_symbols.get(normalized_symbol)
        if cached is not None:
            return cached
        with self._exact_lock:
            cached = self._exact_symbols.get(normalized_symbol)
            if cached is None:
                cached = [
                    dict(row)
                    for row in conn.execute(
                        f"SELECT * FROM {table} WHERE normalized_symbol = ? LIMIT ?",
                        (normalized_symbol, limit),
                    )
                ]
                self._exact_symbols[normalized_symbol] = cached
        return cached

    @staticmethod
    def _append_fts_shortlist(
        conn: sqlite3.Connection,
        table: str,
        terms: list[str],
        rows_by_id: dict[int, dict[str, Any]],
        limit: int,
    ) -> None:
        if not _sqlite_object_exists(conn, "symbols_fts"):
            return
        for term in terms[:4]:
            tokens = [token for token in term.split() if len(token) >= 2]
            if not tokens:
                continue
            expression = " OR ".join(f'"{token.replace(chr(34), "")}"*' for token in tokens)
            try:
                rows = conn.execute(
                    f"SELECT s.* FROM symbols_fts f JOIN {table} s ON s.id = f.rowid "
                    "WHERE symbols_fts MATCH ? ORDER BY bm25(symbols_fts) LIMIT ?",
                    (expression, min(limit, 100)),
                )
                for row in rows:
                    rows_by_id.setdefault(int(row["id"]), dict(row))
            except sqlite3.OperationalError:
                return
            if len(rows_by_id) >= limit:
                return


def _append_ngram_shortlist(
    connection: sqlite3.Connection,
    table: str,
    grams: tuple[str, ...],
    rows_by_id: dict[int, dict[str, Any]],
    limit: int,
) -> None:
    selected = tuple(dict.fromkeys(gram for gram in grams if gram))[:24]
    if not selected:
        return
    placeholders = ",".join("?" for _ in selected)
    candidate_ids = [
        int(row[0])
        for row in connection.execute(
            f"SELECT symbol_id, COUNT(DISTINCT gram) AS hits FROM name_ngrams "
            f"WHERE gram IN ({placeholders}) GROUP BY symbol_id "
            "ORDER BY hits DESC LIMIT ?",
            (*selected, min(limit, 100)),
        )
    ]
    if not candidate_ids:
        return
    id_placeholders = ",".join("?" for _ in candidate_ids)
    for row in connection.execute(
        f"SELECT * FROM {table} WHERE id IN ({id_placeholders}) LIMIT ?",
        (*candidate_ids, min(limit, 100)),
    ):
        rows_by_id.setdefault(int(row["id"]), dict(row))


class FinanceDatabaseProvider(PublicProvider):
    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        try:
            import financedatabase as fd  # type: ignore[import-not-found]
        except ImportError:
            return [], [], ProviderError(
                self.meta.provider_id,
                "dependency_missing",
                "FinanceDatabase is not installed; symbol universe fallback was skipped.",
            )
        try:
            dataset = fd.Equities().select()
            rows = _records_from_symbol_dataset(dataset)
        except Exception:  # noqa: BLE001
            return [], [], ProviderError(
                self.meta.provider_id,
                "provider_unavailable",
                "FinanceDatabase symbol universe is unavailable in this runtime.",
            )
        results = parse_symbol_universe_records(rows, query, provider_id=self.meta.provider_id, provider=self.meta.display_name)
        return results[:limit], [], None if results else ProviderError(
            self.meta.provider_id,
            "empty",
            "FinanceDatabase returned no matching symbol metadata.",
        )


class ChinaHkSymbolProvider(PublicProvider):
    """Fast, bundled A-share and Hong Kong security master-data provider."""

    index_path = CHINA_HK_INDEX_PATH
    FUZZY_SHORTLIST_LIMIT = 100

    def __init__(self, meta: ProviderMeta, key_store: ApiKeyStore, http: PublicHttpClient, cache: ApiCache | None = None) -> None:
        super().__init__(meta, key_store, http, cache)
        self.index_manager = SearchIndexManager.for_path(self.index_path)
        self.last_timing: dict[str, float | int] = {}

    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        if not self.index_path.exists():
            return [], [], ProviderError(self.meta.provider_id, "index_missing", "内置中国及港股证券索引缺失。")
        started = time.perf_counter()
        try:
            rows = self._query(query, min(max(limit * 5, 50), self.FUZZY_SHORTLIST_LIMIT))
            metadata = index_metadata(self.index_path)
        except sqlite3.DatabaseError:
            return [], [], ProviderError(self.meta.provider_id, "index_corrupted", "内置中国及港股证券索引无法读取。")
        results = [_china_hk_result(dict(row), query, self.meta, metadata) for row in rows]
        results.sort(key=lambda item: item.match_score, reverse=True)
        self.last_timing = {
            "sqlite_ms": (time.perf_counter() - started) * 1000,
            "shortlist_size": len(rows),
            "fuzzy_ms": 0.0,
        }
        selected = results[:limit]
        return selected, [], None if selected else ProviderError(self.meta.provider_id, "empty", "内置中国及港股索引没有匹配结果。")

    def profile(self, company: CompanyResult) -> tuple[CompanyProfile | None, ProviderError | None]:
        if not self.index_path.exists():
            return None, ProviderError(self.meta.provider_id, "index_missing", "内置中国及港股证券索引缺失。")
        symbol = normalize_china_hk_symbol(company.symbol, company.market or company.exchange)
        try:
            connection = self.index_manager.connection()
            row = connection.execute("SELECT * FROM symbols WHERE normalized_symbol=? LIMIT 1", (symbol,)).fetchone()
        except sqlite3.DatabaseError:
            return None, ProviderError(self.meta.provider_id, "index_corrupted", "内置中国及港股证券索引无法读取。")
        if not row:
            return None, ProviderError(self.meta.provider_id, "empty", "内置中国及港股索引没有该证券详情。")
        raw = dict(row)
        profile = CompanyProfile(
            id=str(raw.get("id") or ""),
            display_name=_clean(raw.get("chinese_name")) or _clean(raw.get("name")) or company.display_name,
            legal_name=_clean(raw.get("long_name")),
            short_name=_clean(raw.get("short_name")),
            aliases=[item for item in {_clean(raw.get("chinese_name")), _clean(raw.get("english_name")), _clean(raw.get("short_name"))} if item],
            symbol=_clean(raw.get("symbol")),
            normalized_symbol=_clean(raw.get("normalized_symbol")),
            exchange=_clean(raw.get("exchange")),
            market=_clean(raw.get("market")),
            country=_clean(raw.get("country")),
            region=_clean(raw.get("region")),
            currency=_clean(raw.get("currency")),
            sector=_clean(raw.get("sector")),
            industry=_clean(raw.get("industry")),
            instrument_type=_clean(raw.get("instrument_type")) or "equity",
            listing_date=_clean(raw.get("listing_date")),
            is_listed=True,
            company_type="listed_company",
            official_source_url="https://github.com/akfamily/akshare",
            source_urls=["https://github.com/akfamily/akshare"],
            provider_sources=[self.meta.provider_id],
            updated_at=_clean(raw.get("generated_at")),
            raw={**raw, "from_local_index": True, "is_realtime": False},
        )
        profile.field_sources = _field_sources(profile, self.meta.provider_id)
        return profile, None

    def _query(self, query: str, limit: int) -> list[sqlite3.Row]:
        terms = expand_query_aliases({query}, max_terms=18)
        plan = build_search_query_plan(query)
        connection = self.index_manager.connection()
        rows: dict[int, sqlite3.Row] = {}
        for term in terms:
            symbol = normalize_china_hk_symbol(term)
            for row in connection.execute("SELECT * FROM symbols WHERE normalized_symbol=? LIMIT 4", (symbol,)):
                rows[int(row["id"])] = row
        if rows and plan.query_type != "name":
            return list(rows.values())[:limit]
        normalized_terms = [remove_company_suffix(term) for term in terms if remove_company_suffix(term)]
        for normalized in normalized_terms[:12]:
            for row in connection.execute("SELECT * FROM symbols WHERE normalized_name=? LIMIT ?", (normalized, limit)):
                rows[int(row["id"])] = row
            for row in connection.execute(
                "SELECT s.* FROM aliases a JOIN symbols s ON s.id=a.symbol_id WHERE a.normalized_alias=? LIMIT ?",
                (normalized, min(limit, 30)),
            ):
                rows[int(row["id"])] = row
        if rows:
            return list(rows.values())[:limit]
        for normalized in normalized_terms[:4]:
            upper = f"{normalized}\uffff"
            for row in connection.execute(
                "SELECT * FROM symbols WHERE normalized_name>=? AND normalized_name<? LIMIT ?",
                (normalized, upper, min(limit, 60)),
            ):
                rows[int(row["id"])] = row
            for row in connection.execute(
                "SELECT s.* FROM aliases a JOIN symbols s ON s.id=a.symbol_id "
                "WHERE a.normalized_alias>=? AND a.normalized_alias<? LIMIT ?",
                (normalized, upper, min(limit, 60)),
            ):
                rows[int(row["id"])] = row
        if len(rows) < limit and plan.ngrams and self.index_manager.has_object("name_ngrams"):
            converted = {key: dict(value) for key, value in rows.items()}
            _append_ngram_shortlist(connection, "symbols", plan.ngrams, converted, limit)
            rows = {key: value for key, value in converted.items()}
        if len(rows) < limit and plan.allow_fuzzy and self.index_manager.has_object("symbols_fts"):
            for token in plan.fts_terms[:4]:
                expression = f'"{token}"*'
                try:
                    for row in connection.execute(
                        "SELECT s.* FROM symbols_fts f JOIN symbols s ON s.id=f.rowid "
                        "WHERE symbols_fts MATCH ? ORDER BY bm25(symbols_fts) LIMIT ?",
                        (expression, min(limit, 100)),
                    ):
                        rows[int(row["id"])] = row
                except sqlite3.OperationalError:
                    break
        return list(rows.values())[:limit]


class AkShareProvider(PublicProvider):
    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        try:
            import akshare as ak  # type: ignore[import-not-found]
        except ImportError:
            return [], [], ProviderError(
                self.meta.provider_id,
                "dependency_missing",
                "AKShare is not installed; experimental China/HK fallback was skipped.",
            )
        results: list[CompanyResult] = []
        errors: list[ProviderError] = []
        for loader, market in (
            ("stock_info_a_code_name", "CN"),
            ("stock_hk_spot_em", "HK"),
        ):
            key = cache_key(self.meta.provider_id, loader, {"market": market}, "symbol_list")
            cached = self.cache.get(key) if self.cache else None
            try:
                if isinstance(cached, list):
                    rows = [dict(item) for item in cached if isinstance(item, dict)]
                else:
                    func = getattr(ak, loader)
                    rows = _records_from_symbol_dataset(func())
                    if self.cache and rows:
                        self.cache.set(key, rows, ttl_seconds=86400)
                results.extend(parse_akshare_records(rows, query, market=market))
            except Exception:  # noqa: BLE001
                stale = self.cache.get_stale(key) if self.cache else None
                if isinstance(stale, list):
                    rows = [dict(item) for item in stale if isinstance(item, dict)]
                    results.extend(parse_akshare_records(rows, query, market=market))
                    continue
                errors.append(
                    ProviderError(
                        self.meta.provider_id,
                        "provider_unavailable",
                        f"AKShare {market} public symbol list is unavailable.",
                    )
                )
        ranked = sorted(results, key=lambda item: item.match_score, reverse=True)[:limit]
        if ranked:
            return ranked, [], None
        return [], [], errors[0] if errors else ProviderError(
            self.meta.provider_id,
            "empty",
            "AKShare returned no matching China/HK symbol metadata.",
        )

    def profile(self, company: CompanyResult) -> tuple[CompanyProfile | None, ProviderError | None]:
        symbol = normalize_china_hk_symbol(company.symbol, company.market or company.exchange)
        if not symbol:
            return None, ProviderError(self.meta.provider_id, "empty", "AKShare profile requires a China/HK symbol.")
        endpoint = "stock_hk_company_profile_em" if symbol.startswith("HK") else "stock_individual_info_em"
        key = cache_key(self.meta.provider_id, endpoint, {"symbol": symbol}, "profile")
        cached = self.cache.get(key) if self.cache else None
        from_cache = isinstance(cached, dict)
        raw = dict(cached) if isinstance(cached, dict) else {}
        if not raw:
            try:
                import akshare as ak  # type: ignore[import-not-found]

                frame = getattr(ak, endpoint)(symbol=symbol[2:])
                raw = _akshare_profile_dict(frame)
                if self.cache and raw:
                    self.cache.set(key, raw, ttl_seconds=86400)
            except ImportError:
                return None, ProviderError(self.meta.provider_id, "dependency_missing", "内置 AKShare 运行依赖缺失。")
            except Exception as exc:  # noqa: BLE001
                stale = self.cache.get_stale(key) if self.cache else None
                if isinstance(stale, dict):
                    raw = dict(stale)
                    from_cache = True
                else:
                    state = "network_timeout" if "timeout" in str(exc).casefold() else "provider_unavailable"
                    return None, ProviderError(self.meta.provider_id, state, "中国及港股公开资料来源暂时不可用。")
        if not raw:
            return None, ProviderError(self.meta.provider_id, "empty", "AKShare 未返回该公司的公开详情。")
        profile = CompanyProfile(
            display_name=_clean(_first_present(raw, "股票简称", "公司名称", "中文名称", "名称")) or company.display_name or company.name,
            legal_name=_clean(_first_present(raw, "公司全称", "英文名称", "name")),
            short_name=_clean(_first_present(raw, "股票简称", "中文名称", "名称")),
            aliases=list(company.aliases),
            symbol=symbol,
            normalized_symbol=symbol,
            exchange=company.exchange or ("HKEX" if symbol.startswith("HK") else "SSE" if symbol.startswith("SH") else "SZSE"),
            market=company.market or symbol[:2],
            country=company.country or ("Hong Kong" if symbol.startswith("HK") else "China"),
            region=_clean(_first_present(raw, "地区", "地域", "region")),
            sector=_clean(_first_present(raw, "板块", "sector")),
            industry=_clean(_first_present(raw, "行业", "industry")),
            description=_clean(_first_present(raw, "公司简介", "简介", "description")),
            business_scope=_clean(_first_present(raw, "主营业务", "经营范围", "business_scope")),
            website=_clean(_first_present(raw, "官网", "公司网址", "website")),
            listing_date=_clean(_first_present(raw, "上市日期", "上市时间", "listing_date")),
            instrument_type="equity",
            is_listed=True,
            company_type="listed_company",
            provider_sources=["akshare"],
            updated_at=_now(),
            from_cache=from_cache,
            raw={"akshare": raw, "experimental": True, "function_used": endpoint},
        )
        profile.field_sources = _field_sources(profile, "akshare")
        return profile, None


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
        lei = company.lei
        resolved: CompanyResult | None = None
        if not lei:
            names = [company.legal_name, company.display_name, company.name, *company.aliases]
            minimum_length = 4 if company.symbol or company.country else 6
            query = next(
                (name for name in names if len(remove_company_suffix(name).strip()) >= minimum_length),
                "",
            )
            if not query:
                return None, ProviderError(self.meta.provider_id, "empty", "没有足够明确的法人名称用于 GLEIF 查询。")
            candidates, _news, search_error = self.search(query, limit=8)
            if search_error and not candidates:
                return None, search_error
            ranked = sorted(candidates, key=lambda item: _gleif_candidate_score(company, item), reverse=True)
            if not ranked or _gleif_candidate_score(company, ranked[0]) < 90:
                return None, ProviderError(self.meta.provider_id, "empty", "GLEIF 返回了歧义候选，未自动采用。")
            if len(ranked) > 1 and _gleif_candidate_score(company, ranked[0]) - _gleif_candidate_score(company, ranked[1]) < 8:
                return None, ProviderError(self.meta.provider_id, "empty", "GLEIF 法人名称匹配存在歧义，未自动采用。")
            resolved = ranked[0]
            lei = resolved.lei
        data, error = self.http.get_json(
            self.meta.provider_id,
            f"https://api.gleif.org/api/v1/lei-records/{lei}",
        )
        if error:
            return None, error
        results = parse_gleif_records({"data": [data.get("data")]} if isinstance(data, dict) else data, lei)
        if not results:
            return None, ProviderError(self.meta.provider_id, "empty", "GLEIF profile returned no data.")
        result = results[0]
        raw = result.raw
        attrs = raw.get("attributes") or {}
        entity = attrs.get("entity") or {}
        registration = attrs.get("registration") or {}
        legal_address = entity.get("legalAddress") or {}
        headquarters = entity.get("headquartersAddress") or {}
        profile = CompanyProfile(
            display_name=company.display_name or result.legal_name or result.name,
            legal_name=result.legal_name or result.name,
            lei=result.lei,
            country=result.country,
            country_code=_clean(legal_address.get("country")),
            jurisdiction=result.jurisdiction,
            entity_status=_clean(entity.get("status")),
            registration_status=_clean(registration.get("status")),
            legal_address=_format_address(legal_address),
            registered_address=_format_address(legal_address),
            address=_format_address(headquarters) or _format_address(legal_address),
            entity_type=_clean(entity.get("category")),
            company_type="legal_entity",
            official_source_url=result.source_url,
            source_urls=[result.source_url] if result.source_url else [],
            provider_sources=["gleif"],
            updated_at=_now(),
            raw={"gleif": raw, "resolved_by_name": bool(resolved)},
        )
        profile.field_sources = _field_sources(profile, "gleif")
        return profile, None


class WikidataProvider(PublicProvider):
    def search(self, query: str, limit: int = 10) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        language = "zh" if any("\u4e00" <= char <= "\u9fff" for char in query) else "en"
        data, error = self.http.get_json(
            self.meta.provider_id,
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbsearchentities",
                "format": "json",
                "language": language,
                "uselang": language,
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
            terms = [company.legal_name, company.display_name, company.name, *company.aliases]
            terms.extend(expand_query_aliases({item for item in terms if item}, max_terms=12))
            candidates: list[CompanyResult] = []
            last_error: ProviderError | None = None
            for term in list(dict.fromkeys(item.strip() for item in terms if item.strip()))[:4]:
                found, _news, search_error = self.search(term, limit=8)
                candidates.extend(found)
                last_error = search_error or last_error
                if any(_wikidata_candidate_score(company, item) >= 90 for item in found):
                    break
            ranked = sorted(candidates, key=lambda item: _wikidata_candidate_score(company, item), reverse=True)
            if not ranked or _wikidata_candidate_score(company, ranked[0]) < 80:
                return None, last_error or ProviderError(
                    self.meta.provider_id,
                    "empty",
                    "未找到高置信度公开实体信息。",
                )
            qid = ranked[0].wikidata_id
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
        if not _wikidata_profile_matches_company(company, profile):
            return None, ProviderError(
                self.meta.provider_id,
                "empty",
                "Wikidata 候选与公司身份不一致，未自动采用。",
            )
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

    def search_cached(
        self, query: str, limit: int = 10
    ) -> tuple[list[CompanyResult], list[NewsItem], ProviderError | None]:
        """Search downloaded directory files without performing network I/O."""
        all_results: list[CompanyResult] = []
        cache_found = False
        for url, source in [(NASDAQ_LISTED_URL, "nasdaqlisted"), (NASDAQ_OTHER_LISTED_URL, "otherlisted")]:
            key = cache_key(self.meta.provider_id, url, {}, "")
            text = self.cache.get_stale(key) if self.cache else None
            if not isinstance(text, str):
                continue
            cache_found = True
            rows = parse_nasdaq_directory(text, query, source=source)
            for row in rows:
                row.from_cache = True
            all_results.extend(rows)
        ranked = sorted(
            _dedupe_company_results(all_results), key=lambda item: item.match_score, reverse=True
        )[:limit]
        if ranked:
            return ranked, [], None
        state = "empty" if cache_found else "cache_miss"
        message = (
            "Nasdaq 本地目录缓存没有返回匹配结果。"
            if cache_found
            else "Nasdaq 本地目录尚未缓存，已跳过首屏查询。"
        )
        return [], [], ProviderError(self.meta.provider_id, state, message)

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
        "rss": RssNewsProvider,
        "symbol_universe": SymbolUniverseProvider,
        "china_hk_symbol_index": ChinaHkSymbolProvider,
        "finance_database": FinanceDatabaseProvider,
        "akshare": AkShareProvider,
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
        is_etf=_bool_or_none(row.get("isEtf")),
        is_actively_trading=_bool_or_none(row.get("isActivelyTrading")),
        is_adr=_bool_or_none(row.get("isAdr")),
        is_fund=_bool_or_none(row.get("isFund")),
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


def parse_rss_news(text: str, *, query: str, provider_name: str = "RSS News") -> list[NewsItem]:
    parsed = feedparser.parse(text or "")
    entries = getattr(parsed, "entries", []) or []
    results = []
    for entry in entries:
        title = _clean(getattr(entry, "title", ""))
        if not title:
            continue
        results.append(
            NewsItem(
                id=_clean(getattr(entry, "id", "")),
                title=title,
                provider=provider_name,
                provider_id="rss",
                source=_clean(getattr(entry, "source", {}).get("title", "") if isinstance(getattr(entry, "source", {}), dict) else provider_name),
                published_at=_clean(getattr(entry, "published", "") or getattr(entry, "updated", "")),
                url=_clean(getattr(entry, "link", "")),
                snippet=_clean(getattr(entry, "summary", ""))[:240],
                entities=[{"query": query}],
            )
        )
    return results


def parse_symbol_universe_records(
    rows: list[dict[str, Any]],
    query: str,
    *,
    provider_id: str = "finance_database",
    provider: str = "FinanceDatabase Symbol Universe",
    source_url: str = "https://github.com/JerBouma/FinanceDatabase",
    generated_at: str = "",
) -> list[CompanyResult]:
    results: list[CompanyResult] = []
    query_terms = {query, *expand_query_aliases({query}, max_terms=16)}
    for row in rows:
        symbol = _clean(_first_present(row, "symbol", "Symbol", "ticker", "Ticker", "code"))
        name = _clean(_first_present(row, "name", "Name", "company", "Company", "longName", "shortName"))
        if not symbol and not name:
            continue
        aliases = _symbol_universe_aliases(symbol, name, _clean(row.get("aliases_json")))
        normalized_symbol = _normalize_symbol_for_index(symbol)
        exact_symbol = any(_normalize_symbol_for_index(term) == normalized_symbol for term in query_terms)
        candidate_terms = tuple(dict.fromkeys((symbol, name, *aliases)))[:8]
        score = 100 if exact_symbol else max(
            shortlist_fuzzy_score(term, candidate)
            for term in tuple(query_terms)[:8]
            for candidate in candidate_terms
        )
        if score < 55:
            continue
        exchange = _clean(_first_present(row, "exchange", "Exchange", "exchangeShortName", "market"))
        country = _clean(_first_present(row, "country", "Country"))
        sector = _clean(_first_present(row, "sector", "Sector", "industry", "Industry"))
        market = _market_from_symbol_universe(symbol, exchange, _clean(_first_present(row, "market", "Market", "category")))
        display_symbol = _display_symbol_for_symbol_universe(symbol)
        results.append(
            CompanyResult(
                name=name or display_symbol,
                display_name=name or display_symbol,
                symbol=display_symbol,
                exchange=exchange,
                market=market,
                country=country,
                aliases=aliases,
                category="financial",
                provider=provider,
                provider_id=provider_id,
                source_url=source_url,
                match_reason="Open-source symbol universe match",
                match_score=score,
                updated_at=generated_at or _now(),
                raw={
                    "from_local_index": True,
                    "is_realtime": False,
                    "source": "FinanceDatabase",
                    "index_generated_at": generated_at,
                    "original_symbol": symbol,
                    "currency": _clean(row.get("currency")),
                    "sector": sector,
                    "industry": _clean(row.get("industry")),
                    "instrument_type": _clean(row.get("instrument_type")) or "equity",
                    "provider_sources": [provider_id],
                    **row,
                },
            )
        )
    return sorted(
        results,
        key=lambda item: (
            item.match_score,
            _symbol_universe_rank_bonus(query_terms, item),
            -len(item.symbol or ""),
        ),
        reverse=True,
    )


def _symbol_universe_query_terms(query: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        cleaned = _clean(value)
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            terms.append(cleaned)

    add(query)
    for alias in expand_query_aliases({query}, max_terms=16):
        add(alias)
    for term in list(terms):
        normalized = _normalize_symbol_for_index(term)
        add(normalized)
        add(normalized.replace(".", "-"))
        add(normalized.replace("-", "."))
        _add_symbol_universe_market_variants(add, normalized)
    return terms


def _add_symbol_universe_market_variants(add: Any, normalized: str) -> None:
    if normalized.startswith("HK"):
        digits = "".join(ch for ch in normalized[2:] if ch.isdigit())
        if digits:
            compact = digits.lstrip("0") or digits
            add(f"{compact.zfill(4)}.HK")
            add(f"{compact.zfill(5)}.HK")
            add(digits.lstrip("0") or digits)
            add(normalize_hk_symbol(normalized))
    elif normalized.startswith("SH"):
        digits = normalized[2:]
        add(f"{digits}.SS")
        add(digits)
        add(normalize_cn_symbol(normalized))
    elif normalized.startswith("SZ"):
        digits = normalized[2:]
        add(f"{digits}.SZ")
        add(digits)
        add(normalize_cn_symbol(normalized))
    elif normalized.isdigit():
        if len(normalized) <= 5:
            add(normalize_hk_symbol(normalized))
            compact = normalized.lstrip("0") or normalized
            add(f"{compact.zfill(4)}.HK")
            add(f"{compact.zfill(5)}.HK")
        if len(normalized) == 6:
            cn = normalize_cn_symbol(normalized)
            add(cn)
            add(f"{normalized}.SS" if cn.startswith("SH") else f"{normalized}.SZ")


def _symbol_universe_aliases(symbol: str, name: str, aliases_json: str) -> list[str]:
    aliases: set[str] = {symbol, name, _display_symbol_for_symbol_universe(symbol)}
    try:
        parsed = json.loads(aliases_json) if aliases_json else []
    except json.JSONDecodeError:
        parsed = []
    if isinstance(parsed, list):
        aliases.update(str(item) for item in parsed if item)
    if symbol.endswith(".HK"):
        digits = symbol.split(".", 1)[0]
        aliases.add(f"HK{digits.zfill(5)}")
        aliases.add(digits.lstrip("0") or digits)
        aliases.add(digits.zfill(5))
    elif symbol.endswith(".SS"):
        digits = symbol.split(".", 1)[0]
        aliases.add(f"SH{digits}")
        aliases.add(digits)
    elif symbol.endswith(".SZ"):
        digits = symbol.split(".", 1)[0]
        aliases.add(f"SZ{digits}")
        aliases.add(digits)
    if symbol == "BRK-B":
        aliases.add("BRK.B")
    return sorted(_clean(item) for item in aliases if _clean(item))


def _symbol_universe_rank_bonus(query_terms: set[str], item: CompanyResult) -> int:
    ordered_terms = list(expand_query_aliases(query_terms, max_terms=24))
    normalized_terms = [_normalize_symbol_for_index(term) for term in ordered_terms]
    candidate_symbols = {_normalize_symbol_for_index(item.symbol), *(_normalize_symbol_for_index(alias) for alias in item.aliases)}
    candidate_name = remove_company_suffix(item.name or item.display_name)
    for index, term in enumerate(normalized_terms):
        raw_term = ordered_terms[index]
        cleaned_term_name = remove_company_suffix(raw_term)
        if term in candidate_symbols:
            return 155 - index
        if term.isdigit() and item.symbol.startswith("HK") and item.symbol[2:].lstrip("0") == (term.lstrip("0") or term):
            return 135 - index
        if len(cleaned_term_name) >= 4 and cleaned_term_name in candidate_name:
            return 120 - index
        if term.startswith("HK"):
            digits = "".join(ch for ch in term[2:] if ch.isdigit())
            compact = digits.lstrip("0") or digits
            if f"{compact.zfill(4)}.HK" in candidate_symbols or f"HK{compact.zfill(5)}" in candidate_symbols:
                return 100 - index
        if term.startswith("SH") and f"{term[2:]}.SS" in candidate_symbols:
            return 100 - index
        if term.startswith("SZ") and f"{term[2:]}.SZ" in candidate_symbols:
            return 100 - index
    if str(item.raw.get("instrument_type") or "").casefold() == "equity":
        return 5
    return 0


def _display_symbol_for_symbol_universe(symbol: str) -> str:
    cleaned = _clean(symbol).upper()
    if cleaned.endswith(".HK"):
        digits = cleaned.split(".", 1)[0]
        return f"HK{digits.zfill(5)}"
    if cleaned.endswith(".SS"):
        return f"SH{cleaned.split('.', 1)[0]}"
    if cleaned.endswith(".SZ"):
        return f"SZ{cleaned.split('.', 1)[0]}"
    if cleaned == "BRK-B":
        return "BRK.B"
    return cleaned


def _market_from_symbol_universe(symbol: str, exchange: str, market: str) -> str:
    cleaned = _clean(symbol).upper()
    exchange_upper = _clean(exchange).upper()
    if cleaned.endswith(".HK") or exchange_upper == "HKG":
        return "HK"
    if cleaned.endswith((".SS", ".SZ")) or exchange_upper in {"SHH", "SHZ"}:
        return "CN"
    if exchange_upper in {"NMS", "NYQ", "ASE", "PCX", "NGM", "NCM"}:
        return "US"
    return market or exchange or ""


def _normalize_symbol_for_index(value: str) -> str:
    return _clean(value).upper().replace("-", ".")


def _normalized_local_terms(terms: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in terms:
        for candidate in (remove_company_suffix(value), " ".join(value.casefold().split())):
            cleaned = candidate.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                normalized.append(cleaned)
    return normalized


def _sqlite_object_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name = ? AND type IN ('table', 'view') LIMIT 1",
        (name,),
    ).fetchone() is not None


def parse_akshare_records(rows: list[dict[str, Any]], query: str, *, market: str) -> list[CompanyResult]:
    results: list[CompanyResult] = []
    for row in rows:
        symbol = _clean(_first_present(row, "代码", "证券代码", "symbol", "code", "Code"))
        name = _clean(_first_present(row, "名称", "股票简称", "name", "Name", "证券简称"))
        if not symbol and not name:
            continue
        score = max(fuzzy_score(query, symbol), fuzzy_score(query, name))
        if score < 55:
            continue
        normalized_symbol = _akshare_symbol(symbol, market)
        results.append(
            CompanyResult(
                name=name or normalized_symbol,
                display_name=name or normalized_symbol,
                symbol=normalized_symbol,
                exchange=_akshare_exchange(normalized_symbol, market),
                market=market,
                country="China" if market == "CN" else "Hong Kong",
                category="financial",
                provider="AKShare Experimental China/HK",
                provider_id="akshare",
                source_url="https://github.com/akfamily/akshare",
                match_reason="AKShare experimental public symbol list match",
                match_score=score,
                updated_at=_now(),
                raw={
                    "experimental": True,
                    "from_public_interface": True,
                    "provider_sources": ["akshare"],
                    **row,
                },
            )
        )
    return sorted(results, key=lambda item: item.match_score, reverse=True)


def _china_hk_result(
    raw: dict[str, Any], query: str, meta: ProviderMeta, metadata: dict[str, str]
) -> CompanyResult:
    symbol = _clean(raw.get("symbol"))
    display_name = _clean(raw.get("chinese_name")) or _clean(raw.get("name"))
    aliases = [
        item
        for item in {
            display_name,
            _clean(raw.get("english_name")),
            _clean(raw.get("short_name")),
            _clean(raw.get("long_name")),
            symbol,
            symbol[2:] if len(symbol) > 2 else "",
        }
        if item
    ]
    exact_symbol = normalize_china_hk_symbol(query, _clean(raw.get("market"))) == symbol
    seed_match = seed_alias_exact_match({query}, set(aliases))
    score = 100 if exact_symbol else max(93 if seed_match else 0, max([fuzzy_score(query, item) for item in aliases] or [0]))
    reason = "股票代码精确匹配" if exact_symbol else ("常用名称或简称匹配" if seed_match else "公司名称相似")
    return CompanyResult(
        id=str(raw.get("id") or ""),
        name=display_name,
        display_name=display_name,
        legal_name=_clean(raw.get("long_name")),
        symbol=symbol,
        exchange=_clean(raw.get("exchange")),
        market=_clean(raw.get("market")),
        country=_clean(raw.get("country")),
        category="listed_company",
        aliases=aliases,
        provider=meta.display_name,
        provider_id=meta.provider_id,
        source_url="https://github.com/akfamily/akshare",
        match_score=score,
        match_reason=reason,
        updated_at=_clean(raw.get("generated_at")) or metadata.get("generated_at", ""),
        raw={
            **raw,
            "provider_sources": [meta.provider_id],
            "provider_category": "bundled_open_source_index",
            "from_local_index": True,
            "is_realtime": False,
        },
    )


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


def _akshare_profile_dict(dataset: Any) -> dict[str, Any]:
    rows = _records_from_symbol_dataset(dataset)
    result: dict[str, Any] = {}
    for row in rows:
        key = _clean(_first_present(row, "item", "项目", "字段", "key"))
        value = _first_present(row, "value", "值", "内容")
        if key:
            result[key] = value
        else:
            for name, candidate in row.items():
                if _clean(candidate):
                    result[str(name)] = candidate
    return result


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
    aliases_data = entity.get("aliases") or {}
    claims = entity.get("claims") or {}
    sitelinks = entity.get("sitelinks") or {}
    label = _language_value(labels, "en") or _language_value(labels, "zh") or qid
    description = _language_value(descriptions, "en") or _language_value(descriptions, "zh")
    title = ((sitelinks.get("enwiki") or {}).get("title") or (sitelinks.get("zhwiki") or {}).get("title") or "")
    wikipedia_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}" if title else ""
    aliases = []
    for language in ("en", "zh", "zh-hans", "zh-hant"):
        for item in aliases_data.get(language, []) if isinstance(aliases_data, dict) else []:
            value = _clean(item.get("value")) if isinstance(item, dict) else ""
            if value and value not in aliases:
                aliases.append(value)
    website = _wikidata_claim_value(claims, "P856")
    symbol = _wikidata_claim_value(claims, "P249")
    inception = _wikidata_claim_value(claims, "P571")
    profile = CompanyProfile(
        display_name=label,
        legal_name=label,
        aliases=aliases,
        symbol=symbol,
        normalized_symbol=_normalize_symbol_for_index(symbol),
        wikidata_id=qid,
        wikipedia_url=wikipedia_url,
        website=website,
        description=description,
        listing_date=inception,
        company_type="encyclopedia_entity",
        official_source_url=f"https://www.wikidata.org/wiki/{qid}",
        source_urls=[url for url in [f"https://www.wikidata.org/wiki/{qid}", wikipedia_url] if url],
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
        score = _symbol_name_score(query, symbol, name)
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


def _rss_search_urls(query: str) -> list[tuple[str, str]]:
    encoded = quote_plus(query)
    return [
        ("Google News RSS", f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"),
        ("Bing News RSS", f"https://www.bing.com/news/search?q={encoded}&format=rss"),
    ]


def _records_from_symbol_dataset(dataset: Any) -> list[dict[str, Any]]:
    if hasattr(dataset, "reset_index"):
        dataset = dataset.reset_index()
    if hasattr(dataset, "to_dict"):
        try:
            records = dataset.to_dict("records")
            if isinstance(records, list):
                return [dict(item) for item in records if isinstance(item, dict)]
        except TypeError:
            pass
    if isinstance(dataset, dict):
        rows = []
        for key, value in dataset.items():
            if isinstance(value, dict):
                row = dict(value)
                row.setdefault("symbol", key)
                rows.append(row)
        return rows
    if isinstance(dataset, list):
        return [dict(item) for item in dataset if isinstance(item, dict)]
    return []


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def _akshare_symbol(symbol: str, market: str) -> str:
    cleaned = _clean(symbol).upper()
    if market == "HK":
        digits = "".join(ch for ch in cleaned if ch.isdigit())
        return f"HK{digits.zfill(5)}" if digits else cleaned
    if market == "CN" and cleaned.isdigit() and len(cleaned) == 6:
        prefix = "SH" if cleaned.startswith("6") else "SZ"
        return f"{prefix}{cleaned}"
    return cleaned


def _akshare_exchange(symbol: str, market: str) -> str:
    if market == "HK":
        return "HKEX"
    if symbol.startswith("SH"):
        return "SSE"
    if symbol.startswith("SZ"):
        return "SZSE"
    return market


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


def _symbol_name_score(query: str, symbol: str, name: str) -> int:
    normalized_query = _normalize_symbol_for_match(query)
    normalized_symbol = _normalize_symbol_for_match(symbol)
    if normalized_query and normalized_query == normalized_symbol:
        return 100
    return max(fuzzy_score(query, symbol), fuzzy_score(query, name))


def _normalize_symbol_for_match(value: str) -> str:
    return "".join(ch for ch in (value or "").upper().replace("-", ".") if ch.isalnum() or ch == ".")


def _looks_like_lei(value: str) -> bool:
    cleaned = value.strip().upper()
    return len(cleaned) == 20 and cleaned.isalnum()


def _wikidata_candidate_score(company: CompanyResult, candidate: CompanyResult) -> int:
    names = [company.legal_name, company.display_name, company.name, *company.aliases]
    candidate_names = [candidate.display_name, candidate.name, *candidate.aliases]
    score = max(
        (fuzzy_score(left, right) for left in names if left for right in candidate_names if right),
        default=0,
    )
    description = candidate.description.casefold()
    if description and _looks_non_organization(description):
        return 0
    if any(word in description for word in ("company", "corporation", "business", "企业", "公司")):
        score = min(100, score + 4)
    elif company.symbol and description and not _looks_like_organization(description):
        score = min(score, 65)
    return score


def _wikidata_profile_matches_company(company: CompanyResult, profile: CompanyProfile) -> bool:
    description = profile.description.casefold()
    if description and _looks_non_organization(description):
        return False
    known_symbols = {
        _normalize_symbol_for_match(company.symbol),
        *(_normalize_symbol_for_match(alias) for alias in company.aliases),
    }
    profile_symbol = _normalize_symbol_for_match(profile.symbol)
    if profile_symbol and known_symbols and profile_symbol not in known_symbols:
        return False
    if company.symbol and not profile_symbol and description and not _looks_like_organization(description):
        return False
    names = [company.legal_name, company.display_name, company.name, *company.aliases]
    return max((fuzzy_score(name, profile.display_name) for name in names if name), default=0) >= 75


def _looks_like_organization(description: str) -> bool:
    terms = (
        "company",
        "corporation",
        "business",
        "enterprise",
        "conglomerate",
        "manufacturer",
        "bank",
        "insurance",
        "technology",
        "automotive",
        "retailer",
        "multinational",
        "公司",
        "企业",
        "集团",
        "银行",
        "保险",
    )
    return any(term in description for term in terms)


def _looks_non_organization(description: str) -> bool:
    terms = (
        "weather station",
        "natural number",
        "integer",
        "village",
        "municipality",
        "human settlement",
        "given name",
        "family name",
        "disambiguation page",
        "film",
        "song",
        "album",
        "railway station",
    )
    return any(term in description for term in terms)


def _gleif_candidate_score(company: CompanyResult, candidate: CompanyResult) -> int:
    names = [company.legal_name, company.display_name, company.name, *company.aliases]
    candidate_name = candidate.legal_name or candidate.name
    normalized_candidate = " ".join(candidate_name.casefold().replace(".", " ").split())
    exact = any(
        " ".join(name.casefold().replace(".", " ").split()) == normalized_candidate
        for name in names
        if name
    )
    score = 100 if exact else max((fuzzy_score(name, candidate_name) for name in names if name), default=0)
    if company.country and candidate.country:
        if _country_matches(company.country, candidate.country):
            score = min(100, score + 8)
        else:
            score = max(0, score - 20)
    if company.jurisdiction and candidate.jurisdiction and company.jurisdiction.casefold() == candidate.jurisdiction.casefold():
        score = min(100, score + 6)
    return score


def _country_matches(left: str, right: str) -> bool:
    aliases = {
        "united states": "us",
        "united states of america": "us",
        "usa": "us",
        "united kingdom": "gb",
        "great britain": "gb",
        "hong kong": "hk",
        "china": "cn",
    }
    left_value = aliases.get(left.strip().casefold(), left.strip().casefold())
    right_value = aliases.get(right.strip().casefold(), right.strip().casefold())
    return left_value == right_value


def _format_address(address: Any) -> str:
    if not isinstance(address, dict):
        return ""
    lines = address.get("addressLines") or []
    values = [*(str(item).strip() for item in lines if str(item).strip())]
    for key in ("city", "region", "postalCode", "country"):
        value = _clean(address.get(key))
        if value and value not in values:
            values.append(value)
    return ", ".join(values)


def _wikidata_claim_value(claims: Any, property_id: str) -> str:
    if not isinstance(claims, dict):
        return ""
    for claim in claims.get(property_id, []):
        try:
            value = claim["mainsnak"]["datavalue"]["value"]
        except (KeyError, TypeError):
            continue
        if isinstance(value, str):
            return value.lstrip("+")[:10] if property_id == "P571" else value
        if isinstance(value, dict) and property_id == "P571":
            return _clean(value.get("time")).lstrip("+")[:10]
    return ""


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


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    cleaned = str(value or "").strip().casefold()
    if cleaned in {"true", "yes", "1"}:
        return True
    if cleaned in {"false", "no", "0"}:
        return False
    return None


def _language_value(data: dict[str, Any], language: str) -> str:
    item = data.get(language) or {}
    return _clean(item.get("value")) if isinstance(item, dict) else ""


def _field_sources(profile: CompanyProfile, provider_id: str) -> dict[str, str]:
    excluded = {
        "raw",
        "field_sources",
        "field_candidates",
        "provider_sources",
        "source_urls",
        "data_coverage",
        "missing_fields",
        "from_cache",
        "schema_version",
    }
    return {
        field: provider_id
        for field, value in profile.to_dict().items()
        if value and field not in excluded
    }


def _now() -> str:
    return utc_timestamp()
