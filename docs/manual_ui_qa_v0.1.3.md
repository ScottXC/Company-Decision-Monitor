# Manual UI QA v0.1.3

Use 1440x900, 1280x720, and Windows 150% scaling. Capture both light and dark themes.

- Dashboard: search is the first action; watchlist rows are readable; no provider diagnostics or fake market data appears.
- Search initial: search field, region, and segmented filters fit without overlap.
- Search results: rows align, long names wrap, match scores/raw URLs are absent, and diagnostics are collapsed.
- Company detail: identity and actions fit on one header row; only real metric values appear; tabs remain reachable.
- News: rows prioritize title/source/time, summaries use no more than two lines, and Xueqiu is a separate external link.
- Watchlist: rows fit at 1280x720; refresh is compact; context menu exposes secondary actions.
- Settings: tabs remain usable, content scrolls vertically, API keys stay masked, and advanced diagnostics do not dominate.
- Dark theme: no white panels, unreadable text, invisible dividers, or broken status colors.
- Keyboard: Ctrl+K focuses global search, Enter submits, Escape dismisses focus, and Tab order reaches all primary controls.
- Packaging: run screenshots from source, then manually inspect the installed and portable builds for identical theme resources.

Generate deterministic screenshots with:

```powershell
python scripts\capture_ui_screenshots.py
```

Output is written to `reports/ui_screenshots/` and is not committed.

## Company data completeness RC1

- Search and open `AAPL`, `腾讯` / `00700`, and `贵州茅台` / `600519`.
- Confirm local name, symbol, exchange/market, country, currency, sector/industry, and instrument type appear before public enrichment where present in the bundled index.
- Confirm the header, summary, overview, securities, registry, source tab, and coverage indicator update after profile enrichment.
- Keep a non-default tab selected during enrichment and confirm it remains selected; confirm scroll position does not jump to the top.
- Switch quickly from AAPL to MSFT, and from Tencent to Kweichow Moutai; stale profile and news results must not replace the current company.
- Confirm profile refresh does not issue a second news request and news retry reloads only news.
- Confirm missing price/market-cap fields create no empty metric cells and no zero values.
- Confirm missing registration data produces one concise message: `当前公开来源暂未返回法人注册资料。`
- Confirm missing news produces `当前公开来源暂未返回相关新闻。`
- Confirm source details show provider state, successful field count, current missing applicable field count, cache state, and update time without raw JSON or tracebacks.
- Confirm cached and stale-fallback profiles render in the same sections and old/corrupt profile caches do not blank the page.
- Confirm AKShare reports optional/dependency-missing and does not block China/Hong Kong local identity fields.
- Confirm crawlergo evidence remains user-triggered and Xueqiu remains external-link-only.
- Validate 1280x720 and Windows 150% scaling for long company names, legal addresses, and source status rows.
- Install with Inno Setup and repeat AAPL profile loading; repeat from the extracted portable ZIP.
- Verify the installer, portable ZIP, and dist tree exclude `.env`, API keys, user cache, watchlist, reports, crawlergo cache, and Xueqiu cookie/token data.
