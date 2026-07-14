# Generalized Search Performance

## Why fixed examples are insufficient

Frequently repeated companies can be fast because their queries hit seed aliases, the recent-query LRU, SQLite's page cache, or an exact-symbol path. Those results do not demonstrate performance for an arbitrary company. The generalized benchmark therefore samples holdout records from the bundled global and China/Hong Kong indexes and excludes known regression queries, golden cases, and seed aliases.

## Performance classes

- **Cold process** starts a new Python process with no in-memory state.
- **Cold query** uses an initialized engine but a query that has not been cached.
- **Warm query** repeats the SQL path while bypassing the application result cache.
- **Cached query** explicitly measures the bounded application LRU.

All benchmark storage uses temporary AppData and cache directories. It cannot modify production search history, watchlists, provider caches, or API settings.

## Query planner

`SearchQueryPlan` classifies symbols, company names, CJK text, and short input. Symbols use exact and prefix paths. Names use exact name/alias, indexed prefix, FTS5, and finally a bounded fuzzy shortlist. Short queries do not run expensive fuzzy matching. Public providers are always scheduled after the local stage.

## SQLite and FTS5

`SearchIndexManager` owns each immutable bundled index once per process. It validates schema once and supplies a separate read-only `mode=ro&immutable=1` connection per worker thread. Exact symbols, exact aliases, and range-based prefixes use B-tree indexes. FTS5 uses `prefix='2 3 4'`, `MATCH`, BM25 ordering, and a `LIMIT`.

## Chinese and name n-grams

The build creates `name_ngrams`. CJK names use deduplicated 2-grams and 3-grams; Latin names use 3-grams as a spelling-error candidate fallback. Runtime SQL groups matching grams through `idx_name_ngrams_gram`, returns at most 100 entity IDs, and only then invokes RapidFuzz. No stock code n-grams are generated.

## RapidFuzz shortlist

Exact and prefix hits do not require a full-universe fuzzy pass. SQL deduplicates candidates by entity ID before mapping. The default provider shortlist is 100 and the combined local hard limit is 200. Each result's aliases are scored as one entity rather than emitted as separate results.

## Generic warmup

After the search page is created, a background worker opens the two indexes, validates schema, reads lightweight metadata, and executes `SELECT 1 ... LIMIT 1`. It does not search Apple, Tencent, or any other fixed company and does not populate query caches.

## Targets

- unseen ticker cold-query p95: 150 ms
- unseen English company name cold-query p95: 400 ms
- unseen Chinese company name cold-query p95: 500 ms
- warm-query p95: 200 ms
- cached-query p95: 50 ms
- local-first p95: 600 ms
- recall@3: 85%
- recall@5: 92%

Use `scripts/benchmark_unseen_search.py` for holdout performance and `scripts/check_search_query_plans.py` for query-plan verification.

## Known limitations

Very short or highly ambiguous prefixes can identify several valid listings. The ranking may choose a different exchange listing of the same company. Cold-process time includes Python and Qt-related import overhead. Public enrichment latency is reported separately and never delays the local result list.
