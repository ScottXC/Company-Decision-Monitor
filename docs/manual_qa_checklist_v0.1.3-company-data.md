# Manual QA Checklist - v0.1.3 Company Data Completeness

## Company matrix

- [ ] Apple / AAPL
- [ ] Microsoft / MSFT
- [ ] IBM
- [ ] 腾讯 / 腾讯控股 / 00700
- [ ] 阿里巴巴 / 09988
- [ ] 贵州茅台 / 600519
- [ ] 比亚迪 / 002594
- [ ] 中国平安 / 601318
- [ ] Toyota / TM
- [ ] TSMC / TSM
- [ ] HSBC
- [ ] Shell

For each case record search result, initial/enriched field counts, identity fields, classification, description, website, legal fields, provider sources, coverage, cache state, and provider errors. Do not treat absent price, market capitalization, news, or legal records as a failure unless a provider returned meaningful values that the UI failed to display.

## Detail loading and switching

- [ ] Local fields render before public enrichment completes.
- [ ] Header, summary, overview, securities, registry, sources, and coverage update after enrichment.
- [ ] Current tab and approximate scroll position remain stable.
- [ ] Profile completion does not trigger a duplicate news request.
- [ ] AAPL -> MSFT rejects stale AAPL profile/news responses.
- [ ] Tencent -> Kweichow Moutai rejects stale Tencent profile/news responses.
- [ ] Closing the application invalidates pending detail callbacks.
- [ ] A provider timeout does not remove already-rendered local fields.

## Data truthfulness

- [ ] Missing price/market cap creates no empty metric or zero value.
- [ ] Missing news shows one concise empty state.
- [ ] Missing registry data shows one concise empty state.
- [ ] Low-confidence Wikidata/GLEIF candidates are not adopted.
- [ ] AKShare dependency-missing is non-blocking.
- [ ] Source diagnostics contain no raw JSON, traceback, API key, cookie, or token.
- [ ] Xueqiu remains a browser-only external link and is not counted as news.

## Cache and storage

- [ ] Current schema profile serializes and renders from cache.
- [ ] Old empty schema cache is ignored safely.
- [ ] Corrupt cache does not crash the page.
- [ ] Stale fallback is labeled as cached.
- [ ] Profile cache handling does not remove the watchlist.

## Windows delivery

- [ ] Dist EXE starts and SQLite/FTS5 self-test passes.
- [ ] Portable ZIP starts after extraction.
- [ ] Installer installs, starts, and uninstalls successfully.
- [ ] 1280x720 has no overlap.
- [ ] 150% DPI does not clip key fields or controls.
- [ ] Artifacts exclude `.env`, API keys, AppData, cache, watchlist, reports, crawlergo cache, and Xueqiu credentials.
