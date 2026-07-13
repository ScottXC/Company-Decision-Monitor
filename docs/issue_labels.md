# Issue Labels

Suggested GitHub labels for Company Decision Monitor.

| Label | Purpose |
|---|---|
| `bug` | Reproducible app behavior defect. |
| `provider` | Provider-specific data, API key, quota, mapping, or fallback issue. |
| `enhancement` | Feature request or product improvement. |
| `installation` | Installer, portable zip, executable launch, uninstall, or Windows environment issue. |
| `api-key-safety` | API key masking, redaction, storage, or leakage concern. |
| `cache` | Cache hit, stale fallback, cache clearing, or cache safety issue. |
| `watchlist` | Local watchlist add, remove, persist, or refresh issue. |
| `search` | Company search, ranking, de-duplication, or no-result behavior. |
| `company-profile` | Company detail, field merge, source attribution, or external link issue. |
| `news` | News aggregation, de-duplication, empty result, or source issue. |
| `xueqiu-external-link` | Xueqiu external browser handoff behavior. No scraping requests. |
| `docs` | README, release notes, QA checklist, or developer documentation. |
| `build` | PyInstaller, portable zip, Inno Setup, release artifact validation. |
| `tests` | Unit tests, smoke tests, manual QA checklist, validation scripts. |
| `needs-triage` | New issue awaiting review and severity classification. |
| `blocked` | Blocked by missing information, upstream provider behavior, or external dependency. |
| `wontfix` | Not planned, out of scope, or conflicts with compliance/product constraints. |

Labeling rules:

- Use `provider` plus the provider name in the issue title when a single provider is involved.
- Use `api-key-safety` for any possible key exposure report, even if unconfirmed.
- Use `xueqiu-external-link` only for external handoff issues; requests for scraping Xueqiu content should be closed as out of scope unless official authorization exists.
- Use `installation` for Windows SmartScreen, installer, portable zip, missing DLL, or launch issues.
- Use `build` for release artifact failures and `tests` for validation or smoke script failures.
