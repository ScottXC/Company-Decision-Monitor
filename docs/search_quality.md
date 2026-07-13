# Search Quality

Version scope: `v0.1.3-bundled-open-source-runtime`

## Open-Source Search Direction

The current default mode is `Open-Source Data Mode`. Normal users do not need API keys. Search uses seed aliases, optional open-source symbol universes, public no-key directories, public entity fallback, RSS fallback, and explicit external links.

## Search Recall Hotfix

`v0.1.3-search-recall-hotfix` adds regression coverage and diagnostics for user-reported search recall failures.

Golden cases are stored in:

- `tests/fixtures/search_quality_cases.json`
- `tests/fixtures/news_quality_cases.json`

The current golden set covers English company names, U.S. symbols, Hong Kong codes, A-share codes, Chinese short names, and common abbreviations including Apple, Microsoft, IBM, Tencent, Alibaba, TSMC, BYD, Kweichow Moutai, Ping An, HSBC, Toyota, Shell, and Berkshire Hathaway.

Run diagnostics:

```powershell
python scripts\diagnose_search.py "腾讯"
python scripts\diagnose_search.py "Apple" --json reports/search_diagnosis_apple.json
python scripts\evaluate_search_quality.py
```

The default diagnostic and evaluation modes do not call real providers. Add `--live` only when validating real configured provider behavior.

## Query Normalization

Search input is normalized before provider calls and ranking:

- trim leading/trailing spaces;
- collapse repeated whitespace;
- normalize full-width / half-width characters with Unicode NFKC;
- normalize Chinese and English punctuation;
- identify U.S. symbols, Hong Kong symbols, A-share symbols, class symbols such as `BRK.B` / `BRK-B`, and LEI-like identifiers;
- remove common English and Chinese company suffixes for matching.
- generate market-aware variants for Hong Kong codes (`700` -> `HK00700`), A-share codes (`600519` -> `SH600519`, `000001` -> `SZ000001`), and U.S. class symbols (`BRK-B` -> `BRK.B`).

The normalized query is used for ranking and cache keys. The original query is preserved for display and provider diagnostics.

## Alias Expansion

`seed_aliases.py` contains a small high-confidence alias list for common public companies and abbreviations. It is used only for query expansion and ranking hints.

It is not a local company database and must not be returned directly as a search result.

Examples:

- 腾讯 -> `Tencent`, `HK00700`, `00700`
- 阿里巴巴 -> `Alibaba`, `BABA`, `HK09988`
- 台积电 -> `TSMC`, `TSM`
- 比亚迪 -> `BYD`
- 贵州茅台 -> `Kweichow Moutai`, `SH600519`
- BRK-B -> `BRK.B`, `Berkshire Hathaway`

Seed aliases are used only as query expansion and ranking hints. They are not a local company universe and are not emitted directly as product search results.

## Fuzzy Scoring

The matcher favors:

- exact symbol / LEI / registry number;
- exact normalized company name;
- seed alias exact matches;
- provider alias exact matches;
- acronym matches;
- strong token/fuzzy matches.

Weak fuzzy matches stay in `possible_matches` and should not be shown as best matches.

## Result Ranking

Ranking priorities:

- exact symbol: highest priority;
- exact normalized name;
- seed or provider alias;
- acronym;
- multi-provider hit;
- listed company with symbol and exchange;
- official financial provider before encyclopedia fallback for symbol searches.

Wikidata / Wikipedia is a useful public entity fallback, but it should not outrank an exact symbol result from FMP, Alpha Vantage, or Nasdaq Symbol Directory.

Low-confidence results are kept in `possible_matches`. They are not mixed into `best_matches`, listed-company groups, or legal-entity groups.

## Result Grouping

Search responses expose stable groups:

- `best_matches`, maximum three items;
- `listed_companies`;
- `legal_entities`;
- `encyclopedia_entities`;
- `news`;
- `possible_matches`.

The same `symbol + exchange`, LEI, Wikidata QID, registry number, or normalized name should not produce repeated primary cards.

Deduplication keeps merged provider sources, aliases, the highest score, non-empty fields, alternate source URLs, and cache state.

## News Recall

News query construction now uses:

- symbol;
- display name;
- legal name;
- seed aliases;
- Chinese aliases;
- English aliases.

If symbol-based news returns empty, providers retry company name and then aliases. News relevance is scored by title/snippet exact company matches, symbol matches, finance-source hints, recency, and provider priority. Xueqiu remains an external link only and is never counted as news.

## Diagnostic Workflow

Use `diagnose_search.py` when a user reports a search miss. Check:

- normalized query;
- detected query type;
- query variants;
- seed aliases used;
- provider call plan;
- provider result counts;
- provider skipped reasons and errors;
- dedup before/after counts;
- top ranked results and match reasons;
- final result groups;
- news query variants.

## Multilingual Search

The current version improves common Chinese names, short names, and English abbreviations, but does not ship a broad local company universe. Provider data remains the source of returned company records.

## Limitations

- Alias seeds are intentionally small.
- Some providers may not support Chinese queries directly.
- Without configured financial/news API keys, coverage depends on public fallbacks.
- Search quality depends on provider availability, rate limits, and returned fields.
