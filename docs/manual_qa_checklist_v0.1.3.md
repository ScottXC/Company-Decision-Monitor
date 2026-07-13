# v0.1.3 Search Performance RC1 Manual QA

## Desktop search

- [ ] Cold launch, search `Apple`, and confirm local results appear before public enrichment.
- [ ] Repeat `Apple` and confirm the warm result is visibly immediate.
- [ ] Type continuously and confirm search starts only after the 350 ms debounce.
- [ ] Press Enter and confirm search starts immediately.
- [ ] Cancel an active search and confirm no stale result replaces the current page.
- [ ] Switch rapidly through `Apple -> AAPL -> Microsoft -> IBM`; only IBM may remain.
- [ ] Switch rapidly through `腾讯 -> 00700 -> 阿里巴巴 -> BABA`; only BABA may remain.
- [ ] Disconnect the network and confirm `AAPL`, `Apple`, `IBM`, and seed aliases still search locally without a blank page.
- [ ] Confirm a missing AKShare dependency is shown as optional/unavailable and does not delay local results.
- [ ] Confirm public enrichment updates results incrementally without resetting scroll or selection.

## Detail loading

- [ ] Open a result and confirm profile loading starts only in company detail.
- [ ] Confirm news has an independent loading/error state and is not requested by ordinary search.
- [ ] Close the window during slow public enrichment and confirm no process remains hung.

## SQLite and packaging

- [ ] Temporarily replace the symbol index with an invalid copy in a development build and confirm a readable index-corruption error.
- [ ] Run installed `CompanyDecisionMonitor.exe --self-test sqlite`; confirm `fts5=ok` and `index=ok`.
- [ ] Extract the portable ZIP and run the same self-test; confirm it passes.
- [ ] Confirm the installer launches the application after installation.
- [ ] Confirm no `.env`, API key, cache, watchlist, report, or crawlergo binary is bundled.
