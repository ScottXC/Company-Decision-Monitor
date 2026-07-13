# Bundled Open-Source Runtime

Version scope: `v0.1.3-bundled-open-source-runtime`

## Why Bundle Runtime Components

The normal Windows user should be able to install Company Decision Monitor and search companies immediately. This release avoids requiring users to install Python, run `pip install`, download open-source projects, apply for API keys, or import local company files.

## Bundling Strategy

- Runtime dependencies required for search quality are bundled by PyInstaller.
- Build-time dependencies are used before packaging to generate compact resources.
- User-specific files such as `.env`, API keys, cache, watchlist data, crawlergo paths, and reports are not bundled.

## FinanceDatabase Symbol Index

FinanceDatabase is used at build time by `scripts/build_symbol_universe.py` to generate:

`src/cdm_desktop/resources/symbol_universe/symbol_universe.sqlite`

The SQLite index contains only search metadata needed by the app:

- symbol
- company/security name
- currency
- exchange / MIC / market
- country
- sector / industry
- instrument type
- normalized symbol/name
- simple aliases
- source metadata

The installed app reads the bundled SQLite index through `SymbolUniverseProvider`. It does not import FinanceDatabase at normal runtime and does not treat the index as realtime market data or a financial database.

## RapidFuzz

RapidFuzz is bundled as a core runtime dependency. It improves:

- fuzzy search;
- alias matching;
- result ranking;
- provider result deduplication;
- news-title similarity.

If RapidFuzz cannot be imported, the app falls back to `difflib`, but the normal packaged app should include RapidFuzz.

## cleanco

cleanco is bundled as a core runtime dependency for English company-name cleaning. Chinese suffix cleaning continues to use the existing local rules.

## AKShare

AKShare remains optional and experimental. It is not required for the default search workflow and may report `dependency_missing` if not present. This avoids increasing package risk and avoids depending on unstable public interfaces for the main user path. Because AKShare is not bundled in this release, its upstream license should be rechecked before any future bundled distribution decision.

## crawlergo

crawlergo is not bundled by default. It is GPL-3.0 and is treated as an optional external binary that users can configure in advanced settings. The app does not vendor crawlergo, does not bundle crawlergo binaries, and does not use crawlergo for Xueqiu or login/cookie/token/captcha bypass.

## Third-Party Notices

The package includes:

- `THIRD_PARTY_NOTICES.md`
- `third_party/licenses/RapidFuzz_LICENSE.txt`
- `third_party/licenses/cleanco_LICENSE.txt`
- `third_party/licenses/FinanceDatabase_LICENSE.txt`

## PyInstaller Data Files

The build script adds:

- `src/cdm_desktop/resources/`
- `THIRD_PARTY_NOTICES.md`
- `third_party/licenses/`

The release validator checks these files exist in the portable zip and PyInstaller output.

## Size Impact

The generated symbol index is approximately tens of MB and increases the portable zip and installer size. This is intentional so ordinary users do not need to download or generate the index themselves.

## Known Limits

- The symbol index is not realtime market data.
- FinanceDatabase coverage is broad but not equivalent to a commercial database.
- Some Chinese/A-share/HK entities may still require public provider fallback or future index improvements.
- RSS news fallback does not guarantee complete media coverage.
- Advanced API Providers remain optional and disabled by default.
