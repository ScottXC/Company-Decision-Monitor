# v0.1.4 RC Manual QA Checklist

## Workspace and isolation

- [ ] Confirm `reports/`, `build/`, pytest cache, benchmark AppData and temporary SQLite files are ignored.
- [ ] Confirm RC scripts use temporary AppData, cache, history, logs and watchlist paths.
- [ ] Confirm the user's real AppData and watchlist are unchanged.

## Unseen and cold search

- [ ] Start the packaged EXE and search a company not present in known benchmark cases.
- [ ] Clear the query cache and repeat with a different unseen company.
- [ ] Search a random ticker, random English full name and random Chinese company name.
- [ ] Confirm local candidates render before public enrichment.
- [ ] Confirm search does not load news or a full profile.
- [ ] Confirm Enter searches immediately and Cancel leaves the window responsive.

## Rapid switching

- [ ] Run Apple -> AAPL -> Microsoft -> IBM.
- [ ] Run Tencent -> 00700 -> Alibaba -> BABA.
- [ ] Run TSMC -> TSM -> Kweichow Moutai -> 600519.
- [ ] Run 20 randomly selected holdout tickers.
- [ ] Confirm only the final query updates the UI and navigation remains usable.

## Offline and failures

- [ ] Disconnect the network and search random local-index companies.
- [ ] Confirm public enrichment reports unavailable without clearing local results.
- [ ] Confirm news reports offline only after opening company details.
- [ ] Confirm Xueqiu remains a system-browser external link.
- [ ] Verify missing, corrupted and schema-incompatible indexes produce readable status errors.
- [ ] Verify missing FTS5/n-gram objects block release validation.

## Packaged runtime

- [ ] Launch the onedir EXE.
- [ ] Extract and launch the Portable ZIP.
- [ ] Install, launch and uninstall the Installer build.
- [ ] Run `CompanyDecisionMonitor.exe --self-test sqlite` in packaged and portable layouts.
- [ ] Confirm exact-symbol, alias, FTS5, n-gram and schema-version checks pass.
- [ ] Confirm closing the application leaves no worker process behind.
- [ ] Confirm no `.env`, key, cookie, token, user cache, watchlist, reports, tests or source tree is packaged.
