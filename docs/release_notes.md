# Release Notes

## v0.1.2-rc1 - Xueqiu External Community Link

Release type: compliance-bounded external source entry for `v0.1.2-core-functions`.

### Completed

- Added Xueqiu external community link provider.
- Added safe symbol-to-Xueqiu URL generation for A-share, Hong Kong, and U.S. symbols.
- Added a Company Profile card for "雪球社区入口".
- Added a secondary search-result action under the advanced fields area when a direct stock link can be generated.
- Added Settings provider status for "雪球社区入口" as an external link source that requires no API key.
- Added release artifact validation for forbidden Xueqiu token/cookie markers.

### Compliance Boundary

- It only opens Xueqiu pages in the system browser after a user click.
- It does not scrape Xueqiu pages.
- It does not call non-public Xueqiu interfaces.
- It does not use user cookies or tokens.
- It does not cache, index, store, summarize, train on, or ingest Xueqiu content into AI/RAG flows.
- It is not counted as a real news provider and is not included in news freshness counts.

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
