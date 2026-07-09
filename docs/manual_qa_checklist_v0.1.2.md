# Manual QA Checklist - v0.1.2

Release: `v0.1.2`
Mode: `Public + Free API Network Mode`

Use this checklist for manual validation before publishing the formal GitHub release.

## Installation And Launch

- [ ] Fresh install on Windows 10/11.
- [ ] First launch succeeds without Python installed.
- [ ] Dashboard shows `Public + Free API Network Mode`.
- [ ] No `UI Preview Mode` text appears.
- [ ] No raw traceback appears on startup.

## Settings And API Keys

- [ ] Settings page can save an FMP key.
- [ ] Settings page can save an Alpha Vantage key.
- [ ] Settings page can save a Marketaux key.
- [ ] Saved keys are masked.
- [ ] Empty fields do not overwrite existing keys.
- [ ] Invalid FMP key shows a clear error.
- [ ] Invalid Alpha Vantage key shows a clear error.
- [ ] Invalid Marketaux key shows a clear error.
- [ ] No-key mode still allows fallback search.

## Search

- [ ] Search `Apple`.
- [ ] Search `AAPL`.
- [ ] Search `IBM`.
- [ ] Search `Microsoft`.
- [ ] Search `MSFT`.
- [ ] Results do not contain fake companies.
- [ ] Provider badges are visible.
- [ ] Provider errors are readable and do not contain tracebacks.
- [ ] Missing providers do not block other providers.

## Company Detail

- [ ] Open company detail from a search result.
- [ ] Profile fields render only real provider-returned data.
- [ ] Missing profile fields show empty/unknown state, not fake zeroes.
- [ ] News list shows title, source, time, provider, and link only.
- [ ] News list does not copy full article text.
- [ ] Provider badges and source details are visible.
- [ ] `from_cache` badge appears when cached data is used.

## Watchlist

- [ ] Add a company to watchlist.
- [ ] Remove a company from watchlist.
- [ ] Refresh one watchlist item.
- [ ] Refresh all watchlist items.
- [ ] Restart the app and verify watchlist persists.
- [ ] Removed watchlist items do not reappear.

## Cache And Offline Behavior

- [ ] Clear cache from Settings.
- [ ] Disconnect network and search a previously cached company.
- [ ] Cache fallback works where stale cache is available.
- [ ] Network errors are readable.
- [ ] Raw traceback, `NoneType`, JSON dumps, and full request URLs with keys are not displayed.

## Xueqiu External Community Entry

- [ ] Company detail shows Xueqiu external entry where applicable.
- [ ] Xueqiu button opens the system browser.
- [ ] The app does not scrape Xueqiu content.
- [ ] The app does not cache Xueqiu content.
- [ ] The app does not provide Xueqiu cookie/token configuration.
- [ ] The app does not show posts, comments, body text, or user speech from Xueqiu.

## Installer And Artifacts

- [ ] Installer completes successfully.
- [ ] Desktop shortcut is optional.
- [ ] Start Menu shortcut works.
- [ ] Uninstall succeeds.
- [ ] `dist` does not contain `.env`.
- [ ] Portable zip does not contain `.env`.
- [ ] Installer does not contain `.env`.
- [ ] Artifacts do not contain API keys.
- [ ] Artifacts do not contain cache.
- [ ] Artifacts do not contain user watchlist data.
- [ ] Artifacts do not contain tests or source directories.

## Release Decision

- [ ] `ruff check src tests scripts` passed.
- [ ] `pytest` passed.
- [ ] `python -m compileall src scripts` passed.
- [ ] `build.bat` passed.
- [ ] `python scripts\validate_release_artifacts.py` passed.
- [ ] `python scripts\hash_release_artifacts.py` generated hashes.
- [ ] Real provider smoke test was run or explicitly skipped with reason.
- [ ] User-flow smoke test was run or explicitly skipped with reason.
