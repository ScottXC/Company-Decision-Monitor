## Summary

<!-- What changed and why? -->

## Scope

<!-- Bug fix / provider mapping / UI / docs / build / tests / release maintenance -->

## Tests Run

- [ ] `ruff check src tests scripts`
- [ ] `pytest`
- [ ] `python -m compileall src scripts`
- [ ] Other:

## Build Run

- [ ] `build.bat`
- [ ] `python scripts\validate_release_artifacts.py`
- [ ] `python scripts\hash_release_artifacts.py`
- [ ] Not needed because:

## API Key Safety Check

- [ ] No real API keys are committed.
- [ ] Logs, cache keys, reports, and error messages redact keys.
- [ ] UI only displays masked keys.

## Packaging Safety Check

- [ ] No `.env` file is included.
- [ ] No user cache is included.
- [ ] No user watchlist is included.
- [ ] No AppData content is included.

## Compliance Check

- [ ] No scraping was added.
- [ ] No unofficial API bypass was added.
- [ ] No cookie/token collection was added.
- [ ] No fake company, news, financial, or risk data was added.

## Screenshots

<!-- Required if UI changed. Remove this section if not applicable. -->
