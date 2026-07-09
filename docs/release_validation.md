# Release Validation - v0.1.2

## Validation Goal

`v0.1.2` is the stable release for the core public-network function loop. The goal is to validate provider-backed search, company profiles, related news, watchlist persistence, cache fallback, API key safety, Xueqiu external handoff, and Windows delivery artifacts before publishing the GitHub release.

## Automated Tests

Run:

```bat
ruff check src tests scripts
pytest
python -m compileall src scripts
```

The pytest suite uses local fixtures, mocked responses, and deterministic provider mapping checks. It must not call real external APIs.

## Real API Smoke Test

Run manually when real keys are configured in AppData, environment variables, or a local untracked `.env` file:

```bat
python scripts\smoke_real_providers.py
```

The script checks:

- FMP connection, AAPL search, AAPL profile, AAPL news.
- Alpha Vantage connection, IBM SYMBOL_SEARCH, IBM OVERVIEW.
- Marketaux connection and AAPL/Apple news.
- Nasdaq Symbol Directory fallback.
- Wikidata / Wikipedia fallback.
- GLEIF fallback.

It skips unconfigured keyed providers and masks all key values.

## User Flow Smoke Test

Run:

```bat
python scripts\smoke_user_flow.py
```

This uses a temporary local data directory and calls the service layer directly. It does not pollute the user's real watchlist or cache.

Validated flow:

1. Search Apple.
2. Search AAPL.
3. Search IBM.
4. Select a best result.
5. Load company detail.
6. Load related news.
7. Add to temporary watchlist.
8. Refresh one watchlist item.
9. Refresh all watchlist items.
10. Remove the temporary watchlist item.

## Manual QA

Use:

```text
docs/manual_qa_checklist_v0.1.2.md
```

Manual QA covers fresh install, first launch, provider settings, search, company detail, news, watchlist persistence, cache fallback, Xueqiu external entry, installer behavior, and artifact inspection.

## Installer Validation

Run:

```bat
build.bat
python scripts\validate_release_artifacts.py
python scripts\hash_release_artifacts.py
```

Required artifacts:

- `dist\CompanyDecisionMonitor\CompanyDecisionMonitor.exe`
- `dist\CompanyDecisionMonitor_Portable.zip`
- `dist\installer\CompanyDecisionMonitor_Setup.exe`

The artifacts must not include `.env`, API keys, AppData, cache, watchlist data, reports, tests, source directories, `.git`, build output, or Xueqiu cookie/token markers.

## Security Validation

Security checks include:

- API key masking.
- Cache key redaction.
- Provider error redaction.
- Smoke report redaction.
- Artifact scan for `.env`, local key files, watchlist files, cache files, and Xueqiu token/cookie markers.
- No raw tracebacks in user-visible error messages.
- No Xueqiu scraping, content caching, content indexing, or AI/RAG ingestion.

## Known Limits

- AI summaries are not implemented.
- Risk rule engine is not implemented.
- Report export is not implemented.
- Full commercial-grade financial data coverage is not implemented.
- Most country-specific official registry providers remain partial or stubbed.
- Xueqiu is only an external browser handoff, not a content provider.

## Pre-Release Checklist

- [ ] Automated tests passed.
- [ ] Build passed.
- [ ] Artifact validation passed.
- [ ] SHA256 hashes generated.
- [ ] Manual QA completed.
- [ ] Real provider smoke test completed or skipped with documented reason.
- [ ] User-flow smoke test completed or skipped with documented reason.
- [ ] Git tag points to the intended RC commit.
- [ ] GitHub Release is marked prerelease.
