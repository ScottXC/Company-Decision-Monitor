# Post-Release Feedback - v0.1.2

## Feedback Goals

The v0.1.2 feedback cycle focuses on validating the released Windows desktop application after real users try the core public-network workflow:

- Search for companies using configured providers and public fallbacks.
- Open company profiles and inspect provider-backed fields.
- Review related news where available.
- Add, refresh, and remove local watchlist entries.
- Verify cache fallback and readable provider errors.
- Confirm installer, portable zip, and direct executable behavior on Windows.

## What Testers Should Try

- Install with the Inno Setup installer.
- Run the portable zip build.
- Launch `CompanyDecisionMonitor.exe` directly.
- Search common symbols such as `AAPL`, `IBM`, or `MSFT`.
- Search a full company name such as `Apple` or `Microsoft`.
- Configure optional free API keys for FMP, Alpha Vantage, or Marketaux.
- Test provider connection status after saving a key.
- Add a search result to the watchlist.
- Refresh one watchlist item and refresh all watchlist items.
- Clear cache and repeat a search.
- Open the Xueqiu external link from a supported company profile.

## How To Report API Key Issues

Use the provider issue template when a key does not work, appears invalid, hits a quota, or produces unexpected provider errors.

Include:

- Provider name.
- Whether a key is configured.
- Whether the UI shows the key as masked only.
- Search keyword or symbol.
- User-visible error message.
- Whether other providers worked.
- Whether cache fallback worked.

Do not include:

- Full API keys.
- `.env` files.
- Full request URLs containing keys or tokens.
- AppData files containing local key storage.

## How To Report Provider Issues

Use the provider issue template for provider-specific behavior:

- Empty result where a provider should return data.
- Rate limit or quota warning.
- Invalid key warning.
- Parse or mapping problem.
- Cache fallback problem.
- Provider status display problem.

If multiple providers fail at the same time, include whether the machine has network access and whether the issue also appears after clearing cache.

## How To Report Installation Issues

Use the bug report template for installer, portable zip, or executable issues.

Include:

- Windows version.
- Package type: Installer, Portable, or EXE.
- Whether the app launches.
- Any Windows SmartScreen, antivirus, or missing DLL message.
- Screenshot of the installer or launch error if available.

## What Information Not To Share

Do not share:

- Full API keys.
- `.env` files.
- `api_keys.json`.
- AppData cache directories.
- Watchlist files if they contain private user preferences.
- Full provider request URLs containing query credentials.
- Xueqiu cookies, access tokens, or session data.

## Known Non-Blocking Warnings

- `datetime.utcnow()` deprecation warnings were cleaned from the public API layer in `v0.1.3-provider-quality`; report any new timezone warnings with the exact command output.
- `build.bat` may print conda activation warnings before falling back to a discovered local Python environment.
- PyInstaller may warn that optional hidden import `pysqlite2` was not found. The packaged app uses the standard SQLite runtime.
- Free-tier providers may return quota or rate-limit warnings depending on the user's account usage.

## Current Unsupported Features

- Investment advice, trading, buy/sell/order workflows, portfolio P&L, target prices, or return forecasts.
- AI summaries.
- Risk rule engine.
- Research report export.
- CSV / Excel / local company database import.
- Deep official registry coverage for complex regions not already implemented.
- Xueqiu scraping, unofficial API calls, cookie/token collection, content caching, content indexing, AI/RAG ingestion, or content summarization.
