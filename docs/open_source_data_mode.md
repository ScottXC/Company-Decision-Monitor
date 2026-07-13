# Open-Source Data Mode

Version scope: `v0.1.3-bundled-open-source-runtime`

## Why This Mode

The project direction changed from a free-API-key workflow to an open-source/no-key default workflow. Normal users should be able to install the desktop app, search companies, maintain a local watchlist, and use public fallback sources without registering third-party API keys.

This mode avoids making ordinary users apply for FMP, Alpha Vantage, Marketaux, Finnhub, NewsAPI, Guardian, OpenCorporates, or similar keys.

## Architecture

Default search uses a layered provider strategy:

1. seed aliases and query expansion;
2. bundled SymbolUniverseProvider, generated from FinanceDatabase equities metadata;
3. Nasdaq Symbol Directory;
4. AKShare experimental China/HK provider, if installed;
5. Wikidata / Wikipedia public entity fallback;
6. GLEIF LEI fallback;
7. RSS News best-effort fallback;
8. Xueqiu external link only;
9. Advanced API Providers only when explicitly enabled.

## Provider Roles

### Bundled Symbol Universe

Used as the default no-key search provider. The installed app reads `symbol_universe.sqlite`, a compact index generated from FinanceDatabase during the build. It improves symbol/name/country/exchange recall but is not a realtime quote, financial statement, or news provider.

If the bundled index is missing or damaged, the provider returns `index_missing` or `index_corrupted` and search continues with other providers.

### RapidFuzz

Used for fuzzy matching, alias matching, provider-result ranking, and news-title de-duplication. The app keeps a difflib fallback if RapidFuzz is unavailable.

### cleanco

Used for English company-name cleaning such as removing Inc, Corp, Ltd, PLC, GmbH, AG, BV, NV, and similar suffixes. The existing Chinese suffix cleaner remains in place.

### AKShare

Used as an optional experimental China/HK symbol provider. It must only use public, no-login, no-cookie, no-token interfaces. If an interface fails, the provider returns `provider_unavailable`, `parse_error`, or `dependency_missing` and does not block the main search flow.

### Wikidata / Wikipedia

Used only as public entity fallback. It is not treated as authoritative financial data.

### GLEIF

Used for LEI and legal-entity fallback. It is not treated as a stock-market data source.

### RSS News

Used as a best-effort news fallback. It reads RSS/Atom metadata only: title, source, timestamp, link, and short feed summary. It does not scrape article bodies.

### Xueqiu

Xueqiu remains an external community link provider only. The app does not scrape, cache, index, summarize, or ingest Xueqiu content and does not use Xueqiu login credentials or access tokens.

## Advanced API Providers

FMP, Alpha Vantage, Marketaux, OpenCorporates, and Companies House are retained for backward compatibility and advanced users. They are disabled by default and are not part of the normal user workflow.

## Cache Strategy

Cache is local, stored under the user AppData directory, and never packaged into the installer. Cache keys must not contain plaintext API keys.

## Compliance Boundaries

- No fake company, news, financial, or risk data.
- No login-gated scraping.
- No cookie/token collection.
- No captcha or anti-bot bypass.
- No Excel/CSV/local company database import mode.
- No AI summary or RAG ingestion in this version.

## Limitations

- Open-source symbol universes are not commercial-grade data products.
- The bundled FinanceDatabase-generated symbol index is not a realtime quote or financial data source.
- AKShare public interfaces can change without notice.
- RSS coverage is incomplete and can return no results.
- Some private companies or low-coverage regions may still not be searchable.
