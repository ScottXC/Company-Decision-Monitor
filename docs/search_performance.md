# Search Performance

## Scope

`v0.1.3-search-performance-rc1` validates the local-first search hotfix without changing provider coverage or the main UI structure. The performance contract is that local results appear first and all public-network enrichment remains optional, asynchronous, and stale-response safe.

## Three-stage pipeline

### 1. Immediate local search

The first stage runs in a Qt worker and uses only:

- query normalization and seed aliases;
- the bundled `symbol_universe.sqlite`;
- the in-memory recent-query cache;
- already downloaded Nasdaq Symbol Directory cache files.

It does not request news, profiles, RSS, web evidence, crawlergo, or Xueqiu content. The final local result limit is 20.

### 2. Background public enrichment

After local results render, Wikidata, GLEIF, AKShare experimental, and other eligible no-key company providers run with limited concurrency. Each network provider uses a short timeout and the stage has an approximately five-second total budget. Results are appended only when their request ID still matches the current query.

### 3. Detail on demand

Company profiles and news start only after a user opens company details. Profile and news workers are independent, so slow news cannot block the profile. RSS, website feeds, web evidence, and external-source links remain detail-level concerns.

## SQLite index

The generated symbol universe contains `symbols` and `aliases` tables plus indexes for normalized symbol, normalized name, exchange, country, and normalized alias. FTS5 is generated when the build-time SQLite supports it; indexed exact and prefix search remain the fallback.

Local lookup order is:

1. exact symbol;
2. exact alias;
3. exact normalized name;
4. symbol/name prefix;
5. alias prefix;
6. bounded FTS/token candidates;
7. bounded contains fallback.

The compatibility view `symbol_universe` remains for older code and tests.

## RapidFuzz shortlist

RapidFuzz never receives the complete symbol universe. SQL returns at most 200 candidates; exact seed-alias symbols commonly return one or two candidates. This removes the previous repeated full-table alias scan and repeated all-candidate fuzzy scoring.

## Debounce and cancellation

- Text input debounce: 350 ms.
- Minimum ordinary text length: 2 characters.
- Structured ticker/identifier input may submit without the ordinary text delay.
- Enter and the Search button submit immediately.
- Every submission increments `search_request_id`.
- Results with an old request ID are discarded and marked cancelled for diagnostics.

Network requests that cannot be physically interrupted are allowed to finish in their worker, but they cannot update the UI after becoming stale.

The search page owns a four-thread `QThreadPool`. A single enrichment request schedules at most four providers and executes at most three concurrently. Cancellation is checked before provider mapping and again before deduplication/ranking. Window shutdown stops accepting searches, marks the active request cancelled, clears queued work, and waits briefly without blocking indefinitely.

## Cache

- Local recent-query LRU: 160 entries, 30-minute TTL.
- Cache key includes normalized query, market hint, region, scope, and limit.
- Background enrichment disk cache: 6 hours.
- Provider response caches retain their existing source-specific TTLs.
- API keys, cookies, and tokens are not part of cache keys or timing logs.

## Timing and slow-query diagnostics

`SearchTiming` records normalization, local index, fuzzy scoring, provider work, deduplication, ranking, rendering, provider timings, cache status, cancellation, result count, and shortlist size. Timings stay in developer logs/diagnostics. Searches over 1,000 ms are logged as slow searches without credentials or page content.

## Performance targets

| Measurement | Target |
|---|---:|
| Warm exact symbol | <= 100 ms |
| Warm local company name | <= 300 ms |
| Local cache hit | <= 50 ms |
| Warm first results | <= 500 ms |
| Cold local index initialization | <= 1,500 ms |

Run:

```powershell
python scripts\benchmark_search.py
```

Use `--public` only when intentionally measuring real public-provider enrichment. The default benchmark is deterministic and local-only.

Release-candidate stress validation:

```powershell
python scripts\stress_search_switching.py
```

It submits three rapid query sequences at 50-150 ms intervals and verifies that only the final request can render, stale requests are cancelled, the bounded pool becomes idle, and neither news nor profile services run.

## Known limitations

- The first process-level index initialization builds a lazy exact-symbol dictionary and is slower than subsequent searches.
- Public-provider tasks that ignore cancellation may continue briefly in background threads, but stale responses are discarded.
- AKShare is optional and experimental; it runs only during background enrichment and may be skipped when unavailable.
- FTS5 improves broad name lookup but is not required for exact/prefix operation.
- Search result coverage remains limited by the bundled open-source index and public sources; this hotfix changes latency, not coverage.
