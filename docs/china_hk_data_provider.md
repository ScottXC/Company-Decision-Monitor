# China and Hong Kong Data Provider

## Scope

`v0.1.4-open-source-data-expansion` bundles AKShare 1.18.64 and a compact China/Hong Kong SQLite security index. Ordinary Windows users do not install Python, run `pip`, configure an API key, or download a master list.

## Bundled index

`china_hk_symbols.sqlite` is generated at build time from AKShare public Shanghai, Shenzhen, Beijing and Hong Kong interfaces. If one upstream is temporarily unavailable, the builder may fill genuine security metadata from the existing FinanceDatabase symbol universe; every row retains its actual `source` and `source_detail`. Empty or fabricated records are rejected.

The database contains `symbols`, `aliases`, `metadata`, and `symbols_fts`. Indexed lookups cover normalized symbol, normalized name, market, exchange, industry and normalized alias. Fuzzy matching is limited to a SQL shortlist.

The bundled snapshot uses schema version 2 and was generated at `2026-07-13T05:57:59.104545+00:00` with AKShare 1.18.64 plus genuine FinanceDatabase fallback rows where recorded. Rebuild and validate it from the project environment with:

```powershell
python scripts\build_china_hk_symbol_index.py
python scripts\validate_china_hk_index.py
```

When an already validated snapshot must be retained during a temporary upstream outage, use `--use-existing`; this does not fabricate or replace records. Source, version, generation time, schema version, A-share/HK counts, and alias count remain in the `metadata` table. The distributed database is point-in-time search metadata, not a realtime market source.

## Runtime provider

`ChinaHkSymbolProvider` is local, enabled by default, and never returns price, market capitalization, news, or invented descriptions. It provides security identity and available classification/listing metadata immediately. `AKShareProvider` is lazy-loaded only after a user opens company details. Its public profile interfaces run in the existing background enrichment worker with cache and stale fallback.

## Routing and cache

Chinese names and A/H-share symbols prefer the bundled China/HK index, then the global symbol universe and public entity sources. Runtime AKShare profile data uses a 24-hour cache. Provider failure is isolated and does not block local search or other profile sources.

## Packaging

PyInstaller collects AKShare submodules and required pandas, NumPy, curl_cffi and parser dependencies. The frozen self-test checks imports and required functions without network access or user-data writes. Release validation checks the database, license, and self-test.

## Compliance

Only public interfaces that require no login, cookie, token, captcha bypass, or anti-bot circumvention are allowed. No Xueqiu interface is used. Xueqiu remains a manual external link and is never scraped, cached, indexed, or counted as news.

## Limitations

AKShare depends on upstream public pages and may temporarily degrade after an upstream change. The bundled index is point-in-time master data, not a realtime quote source. Price, market capitalization, news, legal-registration data, English names, industries and listing dates remain empty when no reliable source returns them.
