# Provider Quality

Version scope: `v0.1.3-provider-quality`

## Provider Health

Provider health tracks:

- provider id and display name;
- current status;
- configured or not configured;
- last checked time;
- last success time;
- last error time;
- last error type and message;
- consecutive failures;
- temporary `disabled_until` for automatic backoff;
- average latency when available.

The dashboard should show only a short summary. Detailed provider state belongs in Settings and diagnostics.

## Error Mapping

Provider errors are mapped to user-readable states:

- `not_configured`;
- `invalid_key`;
- `rate_limited`;
- `quota_exceeded`;
- `premium_endpoint`;
- `network_timeout`;
- `dns_failure`;
- `http_error`;
- `parse_error`;
- `empty_result` / `empty`;
- `provider_unavailable`;
- `cache_miss`.

UI text must not display raw tracebacks, raw exception objects, plaintext API keys, or full request URLs containing credentials.

## Backoff Strategy

Repeated retryable provider failures can trigger a short automatic backoff. This prevents one failing provider from slowing every search.

Manual connection tests bypass backoff so users can verify whether a provider has recovered.

## Fallback Strategy

Search and company detail should continue when a provider fails:

- unconfigured providers are skipped;
- one provider failure does not block other providers;
- stale cache can be used when network requests fail;
- provider errors are recorded in diagnostics instead of replacing the main result area.

## Cache Fallback

Cache keys include provider, endpoint, sanitized params, and normalized query. They must not include plaintext API keys or tokens.

If a cache file is corrupted, the app ignores it and continues. Cache cleanup in Settings deletes public API cache files from the user's AppData directory.

## Known Provider Limitations

- FMP, Alpha Vantage, and Marketaux depend on optional free API keys and free-tier limits.
- Nasdaq Symbol Directory is useful for U.S. listed securities but does not provide full profile or news data.
- Wikidata / Wikipedia is supplemental public entity data, not authoritative financial data.
- GLEIF covers legal entities and LEI records, not market quotes.
- Xueqiu remains an external browser handoff only. It is not a scraper, API provider, news provider, cache source, RAG source, or AI summary source.
