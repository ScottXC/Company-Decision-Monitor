# Release Notes

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
