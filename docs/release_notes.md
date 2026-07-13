# Release Notes

## v0.1.3

Release type: Stable Release.

### Validated

- Fixed asynchronous profile data not refreshing the visible company-detail header and tabs.
- Added immediate local symbol profile mapping from the bundled SQLite index.
- Added confidence-gated automatic Wikidata entity and GLEIF legal-name enrichment.
- Added field-level source tracking and entity-aware profile coverage.
- Added profile cache schema handling and safe rejection of old empty cache entries.
- Hid unsupported empty market metric sections and retained concise empty states.
- Added stale profile/news request rejection when users switch companies quickly.
- Confirmed AKShare is not bundled in this release and its absence does not block local company identity data.
- Documented that public no-key sources can omit live prices, market capitalization, news, and complete legal records.

### Boundaries

- Missing data is not represented as zero, N/A, Unknown, or fabricated content.
- No provider, UI redesign, trading feature, AI summary, risk engine, report export, or Xueqiu ingestion was added.

## v0.1.3 company-data-completeness milestone

### Completed

- Fixed stale company-detail sections after asynchronous profile loading.
- Added bundled Symbol Universe profile lookup for immediate local identity and classification fields.
- Added automatic Wikidata entity resolution when a search result has no QID.
- Added confidence-gated GLEIF legal-name resolution when a search result has no LEI.
- Added experimental China/Hong Kong profile mapping when AKShare is available.
- Expanded the public `CompanyProfile` schema with identity, security, legal, contact, source, and coverage fields.
- Added field-level source tracking, conflict candidates, meaningful-value validation, and profile coverage diagnostics.
- Added profile cache schema versioning so old empty profile caches are not reused indefinitely.
- Hid unsupported empty metric groups and kept a single concise empty state for unavailable sections.

### Boundaries

- Price and market capitalization remain unavailable when no reliable market source returns them.
- AKShare remains optional and experimental. No login, cookie, token, CAPTCHA bypass, or Xueqiu scraping was added.
- Website evidence remains user-triggered and is not automatically merged into a profile.

## v0.1.3 modern-financial-ui milestone

Release type: UI redesign development build.

### Completed

- Rebuilt the application shell with a compact navigation rail, global search field, connection indicator, and theme control.
- Added a unified light/dark/system design system with centralized tokens and QSS resources.
- Rebuilt Dashboard around search, watchlist, real empty states, and a light data-status footer.
- Rebuilt company search as a single-column list and moved technical diagnostics into a collapsed section.
- Rebuilt company profile identity, real-value metrics, tabs, and news rows.
- Rebuilt watchlist rows with search, sorting, compact refresh, and context actions.
- Reorganized Settings into appearance, sources, search, privacy, advanced, and about areas.
- Added reusable avatars, icon buttons, list rows, news rows, metric cells, inline errors, and theme management.
- Preserved local-first search, QThreadPool workers, debounce, stale-request cancellation, and asynchronous enrichment.
- Preserved the Xueqiu external-link-only boundary.

### Boundaries

- No provider, trading feature, fake market data, AI summary, risk engine, report export, local import, or Xueqiu content ingestion was added.
- The design uses general modern financial-tool principles and does not copy Robinhood trademarks or proprietary assets.

## v0.1.3-search-performance-rc1 - Performance Validation Candidate

Release type: release candidate validation in the v0.1.3 line.

### Completed

- Extended the frozen SQLite self-test to verify FTS5, the bundled symbol index schema, and exact/prefix/alias/FTS queries.
- Added cold, warm, cache-hit, repeated-search, shortlist, and background-orchestration measurements for twelve representative queries.
- Added rapid query-switching stress validation with stale-request cancellation and bounded worker-pool checks.
- Opened the bundled symbol index read-only at runtime and added `ANALYZE`/`VACUUM` to index generation.
- Limited the search page to four worker threads, background enrichment to four providers and three concurrent workers, and added cancellation checks before expensive result processing.
- Added offline local-search and release-candidate manual QA coverage.

### Boundaries

- No provider, UI redesign, data coverage, AI summary, risk engine, report export, crawlergo feature, or local data import was added.
- Public provider latency remains external and does not block first local results.
- Xueqiu remains external-link only.

## v0.1.3-search-performance-hotfix - Local-first Search Performance

Release type: P1 performance hotfix in the v0.1.3 line.

### Completed

- Added local-first search so the bundled SQLite index and downloaded Nasdaq cache can render before public providers finish.
- Added indexed `symbols` and `aliases` tables to the bundled symbol universe while keeping the compatibility `symbol_universe` view.
- Limited RapidFuzz scoring to a SQL shortlist of at most 200 candidates.
- Added a 350 ms input debounce, immediate Enter/button submission, and stale request ID cancellation.
- Moved Wikidata, GLEIF, AKShare experimental, and eligible advanced company providers to limited-concurrency background enrichment.
- Removed RSS/news and full company profile work from ordinary search.
- Split company profile and news loading into independent detail-page workers.
- Added `SearchTiming`, slow-search diagnostics, local LRU caching, and `scripts/benchmark_search.py`.
- Preserved the SQLite packaging hotfix and frozen executable SQLite self-test.

### Boundaries

- No provider, data coverage, AI summary, risk engine, report export, crawlergo feature, Xueqiu scraping, or local data import was added.
- Xueqiu remains external-link only and is never counted as news.
- Public enrichment is best-effort and can finish partially when providers exceed the time budget.

## v0.1.3-p0-sqlite-packaging-hotfix - SQLite Runtime Packaging Hotfix

Release type: P0 packaging hotfix in the v0.1.3 line.

### Completed

- Fixed a Windows packaged executable crash caused by a missing SQLite runtime dependency for `_sqlite3`.
- Added dynamic SQLite runtime discovery for PyInstaller builds, including `_sqlite3.pyd` and `sqlite3.dll`.
- Added explicit PyInstaller hidden imports for `sqlite3` and `_sqlite3`.
- Removed the unused `pysqlite2` packaging reference from the generated PyInstaller command.
- Added `CompanyDecisionMonitor.exe --self-test sqlite` so frozen builds can verify SQLite without starting the GUI.
- Updated the Windows build flow to run the frozen SQLite self-test after PyInstaller output validation.
- Updated release artifact validation to run the SQLite self-test and require SQLite runtime files in the portable package and installer source directory.

### Boundaries

- This hotfix only changes startup/package validation for SQLite runtime loading.
- No provider, UI, crawlergo, AI summary, risk rule engine, report export, data model, or search-quality behavior was changed.

## v0.1.3-bundled-open-source-runtime - Bundled Open-Source Runtime

Release type: development build in the v0.1.3 line.

### Completed

- Bundled RapidFuzz for fuzzy matching, alias matching, ranking, deduplication, and news-title similarity.
- Bundled cleanco for English company-name legal suffix cleaning.
- Added `scripts/build_symbol_universe.py` to generate a compact FinanceDatabase-derived local SQLite symbol index.
- Added bundled `src/cdm_desktop/resources/symbol_universe/symbol_universe.sqlite` for no-key company search fallback.
- Added `SymbolUniverseProvider`, which reads the bundled index at runtime and does not require users to install FinanceDatabase.
- Changed the default search provider order to use `symbol_universe` before Nasdaq, AKShare experimental, Wikidata, GLEIF, RSS, and Xueqiu external link.
- Kept FMP, Alpha Vantage, Marketaux, OpenCorporates, and Companies House as Advanced API Providers disabled by default.
- Added `THIRD_PARTY_NOTICES.md` and license files under `third_party/licenses/`.
- Updated PyInstaller build scripts to include notices, license files, and the symbol index while excluding runtime-unneeded FinanceDatabase/AKShare/crawlergo binaries.
- Updated release artifact validation to require notices/licenses/symbol index and continue excluding `.env`, user keys, cache, watchlist, reports, and crawlergo binaries.

### Boundaries

- The bundled symbol universe is not realtime market data and is not a financial statement database.
- AKShare remains optional/experimental and is not required by the normal user workflow.
- crawlergo remains an optional external tool and is not bundled by default.
- No AI summary, risk rule engine, report export, local data import, Xueqiu crawling, cookie/token capture, or captcha/login bypass was added.

## v0.1.3-crawlergo-web-evidence - Controlled Web Evidence Module

Release type: development build in the v0.1.3 line.

### Completed

- Added Crawlergo Web Evidence Provider as an optional binary integration.
- Added `公司相关信息` company-detail section for user-triggered official-site evidence collection.
- Added `网页证据采集` settings section for crawlergo path, max pages, max depth, request delay, timeout, cache TTL, and full-text display option.
- Added robots.txt policy checks, URL safety checks, domain allow-listing, blocked-domain safeguards, and request delay.
- Added short-snippet HTML metadata extraction using BeautifulSoup/lxml.
- Added web evidence cache that stores metadata and snippets only, not full HTML.
- Added tests for robots decisions, command building, URL validation, content extraction, cache behavior, subprocess safety, and UI compliance text.

### Boundaries

- This is not a general crawler, news full-text collector, anti-bot bypass, AI/RAG ingestion path, or training-data collector.
- Xueqiu remains external-link only and is not crawled, cached, indexed, or summarized.
- Login-only, paid, CAPTCHA-protected, social-platform, and unauthorized pages are out of scope.

## v0.1.3-open-source-search - Open-Source Data Mode Development Build

Release type: search and provider-direction development build.

### Completed

- Switched the default mode to `Open-Source Data Mode`.
- Removed the normal-user API key requirement from the default workflow.
- Kept FMP, Alpha Vantage, Marketaux, OpenCorporates, and Companies House code for backward compatibility, but moved them to Advanced API Providers and disabled them by default.
- Added optional FinanceDatabase / Symbol Universe provider with `dependency_missing` fallback when the package is not installed.
- Added optional AKShare experimental China/HK provider with `dependency_missing` / `provider_unavailable` fallback.
- Added RapidFuzz-first fuzzy scoring with difflib fallback.
- Added optional cleanco company-name cleaning with internal suffix-cleaning fallback.
- Updated default search provider order to no-key/open-source sources first: seed aliases, FinanceDatabase, Nasdaq Symbol Directory, AKShare, Wikidata / Wikipedia, GLEIF, RSS, and Xueqiu external link.
- Updated news defaults so RSS News is used before Advanced API news providers.
- Updated settings and dashboard copy to explain that normal users do not need API keys.
- Kept Xueqiu external link only; no scraping, no cookie/token, no cache, no indexing, and no AI/RAG ingestion.

### Still Not Implemented

- AI summaries.
- Risk rule engine.
- Research report export.
- CSV / Excel / local company database import.
- Commercial-grade full data coverage.
- Full AKShare market-data integration.
- Deep official Xueqiu API integration.

## v0.1.3-search-recall-hotfix - Search Recall Development Build

Release type: P1 hotfix build for `Public + Free API Network Mode`.

### Completed

- Added search quality golden cases in `tests/fixtures/search_quality_cases.json`.
- Added news quality golden cases in `tests/fixtures/news_quality_cases.json`.
- Added `scripts/diagnose_search.py` for single-query search diagnostics.
- Added `scripts/evaluate_search_quality.py` for batch recall evaluation.
- Improved query expansion for original query, normalized query, stripped suffixes, symbols, market-prefixed symbols, HK padded symbols, SH/SZ A-share symbols, class-symbol variants, seed aliases, and multilingual aliases.
- Improved Hong Kong symbol detection for `700`, `00700`, `HK00700`, `9988`, `09988`, and `HK09988`.
- Improved A-share symbol detection for `600519`, `SH600519`, `000001`, `SZ000001`, `300750`, and `SZ300750`.
- Improved U.S. class-symbol handling for `BRK.B` and `BRK-B`.
- Expanded high-confidence alias coverage for Apple, Microsoft, Tencent, Alibaba, TSMC, BYD, Kweichow Moutai, Ping An, HSBC, Toyota, Shell, IBM, and Berkshire Hathaway.
- Improved ranking so exact symbols and seed-alias exact matches enter best matches, while weak Wikidata / legal-entity matches do not displace listed-company hits.
- Improved deduplication by symbol + exchange, normalized symbol + market, LEI, Wikidata QID, registry id, and normalized name.
- Improved news query construction and fallback from symbol to company name and aliases.
- Improved news relevance filtering and URL/title de-duplication.
- Kept Xueqiu as external-link only; it is not counted as news and is not scraped, cached, indexed, or summarized.

### Still Not Implemented

- AI summaries.
- Risk rule engine.
- Research report export.
- CSV / Excel / local company database import.
- Commercial-grade full data coverage.
- Complete implementation for most country-specific official registry providers.
- Deep official Xueqiu API integration.

## v0.1.3-provider-quality - Provider Quality Development Build

Release type: quality-focused development build for `Public + Free API Network Mode`.

### Completed

- Updated the application version label to `v0.1.3-provider-quality`.
- Enhanced query normalization for whitespace, full-width / half-width text, company suffixes, Hong Kong symbols, A-share symbols, U.S. class symbols, and LEI-style identifiers.
- Added a small high-confidence seed alias list for query expansion and ranking hints. The alias list is not a local company database and does not return results by itself.
- Improved Chinese, abbreviation, and short-name matching for common searches such as 腾讯, 阿里巴巴, 台积电, 比亚迪, 贵州茅台, 中国平安, HSBC, BYD, and TSMC.
- Added a ranking layer that prioritizes exact symbols, exact normalized names, aliases, acronyms, multi-provider hits, and listed-company records.
- Added stable result grouping for best matches, listed companies, legal entities, encyclopedia entities, news, and possible matches.
- Added lightweight provider health tracking with consecutive failure counts and short automatic backoff for retryable failures.
- Improved company news relevance scoring, title/URL de-duplication, and ordering.
- Improved company profile field merging so empty values do not overwrite better provider fields and field sources remain retained.
- Improved watchlist refresh summaries for single-item and refresh-all flows.
- Improved cache behavior for stable redacted keys, stale fallback, corrupted cache handling, and clear-cache reliability.
- Replaced public API `datetime.utcnow()` usage with timezone-aware UTC timestamps.
- Reduced misleading build environment warning wording in `build.bat`.
- Added `docs/search_quality.md` and `docs/provider_quality.md`.
- Added provider-quality tests for query normalization, seed aliases, ranking, news relevance, profile merge, watchlist refresh, provider health, cache handling, and Xueqiu external-link boundaries.

### Still Not Implemented

- AI summaries.
- Risk rule engine.
- Research report export.
- CSV / Excel / local company database import.
- Commercial-grade full data coverage.
- Complete implementation for most country-specific official registry providers.
- Deep official Xueqiu API integration.

## v0.1.2 - Stable Release

Release type: stable release for `Public + Free API Network Mode`.

### Release Validation Status - 2026-07-09

- `ruff check src tests scripts`: passed.
- `pytest`: passed, 54 tests.
- `python -m compileall src scripts`: passed.
- `build.bat`: passed; exe, portable zip, and Inno Setup installer were regenerated.
- `scripts/validate_release_artifacts.py`: passed.
- `scripts/hash_release_artifacts.py`: passed.
- `scripts/smoke_real_providers.py`: passed with no failed providers; FMP was skipped because no local key was configured.
- `scripts/smoke_user_flow.py`: passed end-to-end with temporary storage.
- No P0/P1/P2 release-blocking issue was found during freeze validation.

### Completed

- Confirmed FMP company profile and news mapping.
- Confirmed Alpha Vantage symbol search and overview mapping.
- Confirmed Marketaux news mapping.
- Confirmed Nasdaq Symbol Directory fallback.
- Confirmed Wikidata / Wikipedia fallback.
- Confirmed GLEIF legal entity fallback.
- Confirmed search aggregation and result grouping.
- Confirmed company detail field merging and field-level provider source tracking.
- Confirmed company news aggregation and de-duplication.
- Confirmed watchlist add, remove, refresh one, and refresh all flows.
- Confirmed cache fallback and stale-cache paths.
- Confirmed API key masking, cache-key redaction, provider error safety, and smoke report redaction.
- Added Xueqiu external community link provider.
- Added safe symbol-to-Xueqiu URL generation for A-share, Hong Kong, and U.S. symbols.
- Added a Company Profile card for "雪球社区入口".
- Added a secondary search-result action under the advanced fields area when a direct stock link can be generated.
- Added Settings provider status for "雪球社区入口" as an external link source that requires no API key.
- Added release artifact validation for exe, portable zip, installer, forbidden user data, and forbidden Xueqiu token/cookie markers.
- Added real provider smoke script.
- Added user-flow smoke script.
- Added SHA256 hash generation script.
- Added manual QA checklist.
- Added release validation guide.

### Compliance Boundary

- It only opens Xueqiu pages in the system browser after a user click.
- It does not scrape Xueqiu pages.
- It does not call non-public Xueqiu interfaces.
- It does not use user cookies or tokens.
- It does not cache, index, store, summarize, train on, or ingest Xueqiu content into AI/RAG flows.
- It is not counted as a real news provider and is not included in news freshness counts.

### Not Complete In This RC

- AI summaries.
- Risk rule engine.
- Research report export.
- Commercial-grade full financial data coverage.
- Complete implementation for most country-specific official registry providers.
- Deep official Xueqiu API integration.

## v0.1.2-core-functions - Core Function Loop

Release type: Windows desktop core-function build for `Public + Free API Network Mode`.

### Completed

- Updated the application version to `v0.1.2-core-functions`.
- Completed provider-backed company search aggregation with configured providers and public fallbacks.
- Implemented FMP company search, company profile mapping, and stock news mapping.
- Implemented Alpha Vantage SYMBOL_SEARCH and OVERVIEW mapping.
- Implemented Marketaux company news mapping.
- Confirmed Nasdaq Symbol Directory fallback parsing and stale-cache fallback.
- Added Wikidata / Wikipedia entity fallback for public company/entity metadata.
- Added GLEIF legal entity fallback mapping.
- Added company profile field merging with field-level provider source tracking.
- Added company news aggregation and de-duplication.
- Added local watchlist single-company refresh and refresh-all flow.
- Added cache fallback paths for search, company profile, news, Nasdaq directory, Wikidata, and GLEIF service usage.
- Added provider error states for missing configuration, invalid keys, quota/rate limits, network timeout, parse errors, empty results, and unavailable providers.
- Added API key safety checks for masking, cache-key redaction, and request-log redaction.
- Updated README with v0.1.2 usage, free API key registration links, cache behavior, and stub provider status.

### Still Stubbed Or Not Yet Complete

- INSEE SIRENE.
- ABN Lookup.
- Japan Corporate Number.
- Singapore ACRA.
- Corporations Canada.
- Guardian.
- NewsAPI.
- RSS / Atom.
- Twelve Data.
- Brazil / India / China / Germany / Netherlands registry strategy.
- AI summaries.
- Risk rule engine.
- Research report export.
- CSV / Excel / local company database import.

### Deliverables

- `dist\CompanyDecisionMonitor\CompanyDecisionMonitor.exe`
- `dist\CompanyDecisionMonitor_Portable.zip`
- `dist\installer\CompanyDecisionMonitor_Setup.exe`

### Security And Privacy Notes

- No real API keys are hardcoded.
- User API keys are not packaged into the installer.
- Cache keys redact API key, token, secret, GUID, `apikey`, and `api_token` values.
- Provider failures are mapped to user-readable states instead of raw tracebacks.
- Watchlist data remains local to the user's machine.

## v0.1.1 - Public + Free API Network Mode

Release type: Windows desktop public-network research build with optional free API key support.

### Highlights

- Updated the application version to `v0.1.1`.
- Updated the application mode to `Public + Free API Network Mode`.
- Added local API key storage with masked key display.
- Added a provider registry and provider status model.
- Added HTTP client error mapping.
- Added local request caching without plaintext API keys in cache keys.
- Added fuzzy search and query helper utilities.
- Added provider mappings for:
  - FMP symbol search and news.
  - Alpha Vantage symbol search.
  - Marketaux news.
  - GLEIF LEI search.
  - Wikidata entity mapping.
  - Nasdaq Symbol Directory parsing.
  - OpenCorporates company search.
  - UK Companies House company search.
  - Norway BRREG company search.
- Added free API key, token, and GUID configuration in Settings.
- Reworked Company Search into a provider-backed search entry point.
- Reworked Company Profile to display provider-returned fields and related news.
- Added local watchlist persistence.
- Updated README with the API matrix, provider registration links, and region coverage strategy.
- Polished the data source settings UI to reduce card spacing and improve information density.

### Stubbed Or Not Yet Complete

- Guardian Open Platform.
- NewsAPI.
- INSEE SIRENE.
- ABN Lookup.
- Japan Corporate Number.
- Singapore ACRA Open Data.
- Corporations Canada.
- Finnhub and Twelve Data.
- Full financial modeling.
- Full risk rule engine.
- AI summaries.
- Research report export.

### Deliverables

- `dist\CompanyDecisionMonitor\CompanyDecisionMonitor.exe`
- `dist\CompanyDecisionMonitor_Portable.zip`
- `dist\installer\CompanyDecisionMonitor_Setup.exe`

### Security And Privacy Notes

- No real API keys are hardcoded.
- User API keys are not packaged into the installer.
- `.env` files are not packaged into the installer.
- Providers without configured keys are skipped automatically.
- Watchlist data and API keys are stored locally on the user's machine.

## v0.1.0 - UI Preview

Release type: Windows desktop UI preview build.

### Highlights

- Added the PyInstaller executable build.
- Added the portable zip build.
- Added the Inno Setup installer build.
- Added the initial desktop UI pages and empty-state design.
