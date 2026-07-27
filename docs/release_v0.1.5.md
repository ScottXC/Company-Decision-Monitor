# Company Decision Monitor v0.1.5

v0.1.5 introduces **Web Evidence（网页证据）**, a user-triggered workflow for collecting and managing allowed public company pages without changing the existing local-first company search path.

## Highlights

- Collect an official company website, investor-relations page, press release, announcement, report page, official blog, or a public URL explicitly entered by the user.
- Enforce public HTTP/HTTPS-only URL validation, redirect revalidation, DNS and connected-peer IP checks, private/metadata address blocking, and same-domain crawl scope.
- Always evaluate `robots.txt`, honor `Disallow` and parsed crawl delay, and identify requests as `CompanyDecisionMonitorBot/0.1.5`.
- Extract bounded metadata, Open Graph fields, headings, links, selected JSON-LD, Organization fields, cleaned text, snippets, dates, language, and content hashes with Beautiful Soup and lxml.
- Display bounded cleaned text for a known official domain; retain only metadata and a short excerpt for third-party pages; keep PDFs metadata-only without downloading or parsing their bodies.
- Store crawl jobs, evidence, links, errors, metadata, and traceable profile-field candidates in the separate user AppData `web_evidence.sqlite` database.
- Run collection in an independent background pool with per-domain serialization, bounded page/depth/time/content limits, cancellation, and safe application-shutdown handling.
- Keep Xueqiu external-link-only and hard-block it from Web Evidence.

## Runtime decision

Crawlergo and Chromium are not bundled. The app can detect and diagnose a bundled, system, or manually configured Crawlergo path, but active Crawlergo discovery is disabled in v0.1.5 because the audited upstream CLI cannot disable form submission and DOM-event triggering. Production collection therefore uses the application's bounded GET-only pipeline. No unknown binary is downloaded.

## Validation

- Ruff: passed.
- Pytest: 214 passed.
- Windows PyInstaller, Portable ZIP, and Inno Setup build: passed.
- Release artifact audit: passed, including exclusion of user databases, cache, credentials, Crawlergo, and browser runtimes.
- Frozen SQLite/FTS5/n-gram, AKShare import, and optional Crawlergo status self-tests: passed.
- Unseen-search benchmark: 450 cases; cold p95 68.885 ms; cache p95 0.254 ms; recall@1/@3/@5 93.75% / 95.75% / 96.75%.
- Search switching, offline search, query-plan checks, and profile coverage: passed.

## Known limitations

- JavaScript-only pages may provide incomplete evidence because active browser discovery is disabled.
- PDF body extraction is deferred; the app retains only PDF metadata and the original link.
- Public no-key sources can be unavailable, incomplete, delayed, rate-limited, or changed upstream.
- AKShare remains an upstream experimental dependency and its public endpoints can change independently.
- This release does not add AI summaries, RAG, risk rules, report export, a search provider, or changes to the bundled symbol indexes.

This GitHub Release intentionally contains no uploaded Windows binary assets; GitHub's automatically generated source archives remain available.
