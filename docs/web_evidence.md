# Web Evidence

Version scope: package `0.1.5`; stable release `v0.1.5`

## Positioning

Web Evidence（网页证据）is a user-triggered company public-page collection and evidence-management module. It is not a web search engine, an automatic news crawler, an anti-bot bypass tool, a website mirror, an AI/RAG knowledge base, or a risk engine. Ordinary company search never starts a Web Evidence job.

Users may start from a verified `CompanyProfile.website`, a Wikidata official website, an existing official source URL, or a public URL they explicitly enter. The normal defaults are 15 pages, depth 2, at least one second between same-domain requests, a 30-second total job timeout, and same-domain-only traversal.

## Runtime and crawlergo decision

`CrawlergoRuntimeManager` can report three discovery modes in this order:

1. Bundled runtime;
2. system `crawlergo` plus Chrome/Chromium;
3. manually configured external runtime.

The v0.1.5 build does **not** bundle crawlergo or Chromium. Crawlergo is GPL-3.0, and the project has not completed the binary/source-offer and browser redistribution work needed for a bundled runtime. More importantly, the audited upstream CLI does not provide a passive mode that disables form submission and DOM-event triggering. The application therefore limits crawlergo integration to optional runtime detection and a no-network diagnostic launch; it does not invoke crawlergo for production URL discovery in this version.

Actual collection uses the application's bounded GET-only pipeline. The settings page reports crawlergo as `dependency_missing` when absent, explains external path configuration, and keeps all other application functions available. No unknown binary is downloaded automatically.

Upstream references:

- https://github.com/Qianlitp/crawlergo
- https://github.com/Qianlitp/crawlergo/blob/master/LICENSE

## URL and SSRF safety

`URLSafetyValidator` allows only `http` and `https`. It rejects:

- `file`, `ftp`, `javascript`, `data`, and other schemes;
- credentials embedded in a URL;
- localhost and loopback addresses;
- private, link-local, multicast, unspecified, reserved, and other non-global IPs;
- common cloud metadata hostnames and metadata IPs;
- Xueqiu, WeChat public accounts, login-only social platforms, and user-configured blocked domains.

Every hostname is resolved before a request. Every resolved IP must be public. Redirects are manual and every target is validated again. Real network requests must expose a connected peer address, and that address is validated before response processing; a missing or unsafe peer address fails closed to reduce DNS-rebinding risk. Proxy environment variables are ignored by the Web Evidence transport. Localhost access exists only behind an explicit development flag and is disabled in normal/frozen builds.

Requests use the explicit user agent `CompanyDecisionMonitorBot/0.1.5`. Callers cannot inject cookies, authorization headers, tokens, or impersonation headers into the Web Evidence fetcher.

## robots.txt

`RobotsPolicy` requests `/robots.txt` before processing each URL origin and evaluates the target path for the application product token. `Disallow` is mandatory and cannot be disabled in normal settings. A blocked page is skipped and shown as “该页面不允许自动采集”. Parsed `Crawl-delay` values are combined with the application's minimum one-second delay.

If robots.txt is absent or temporarily unavailable, the app records that state and uses the minimum low-frequency policy. It never interprets a missing file as permission to bypass authentication, access controls, or a site's technical restrictions.

## Scope and lifecycle

The queue is breadth-first, bounded by page count, depth, total timeout, and allowed domains. Investor relations, press release, announcement, report, financial, news, blog, media, and event paths receive deterministic priority. Login, account, cart, checkout, search, admin, tracking-heavy, unbounded calendar, and unsupported binary URLs are skipped.

Web crawling uses a dedicated `QThreadPool` with at most two jobs. It does not consume search workers or execute on the UI thread. A domain lock allows only one same-domain request at a time. Cancellation uses a `threading.Event`, including during rate-limit waits. Switching companies does not cancel a job; results remain associated with the original company ID. Application shutdown requests safe cancellation and terminates any runtime diagnostic child process.

Crawlergo diagnostics and any future child-process calls use argument lists, `shell=False`, validated executable paths, captured output, a hidden window, and a timeout. Raw stdout/stderr is never rendered in the normal UI.

## Extraction

`WebContentExtractor` uses the already bundled Beautiful Soup and lxml dependencies. It extracts:

- final and canonical URL;
- title, meta description, Open Graph title/description, H1, site name, author, language;
- published and modified timestamps;
- headings and bounded links;
- supported JSON-LD nodes (`Organization`, `Corporation`, `NewsArticle`, `Article`, `PressRelease`, `WebPage`, and `BreadcrumbList`);
- Organization name, alternate/legal name, URL, logo, address, telephone, email, founding date, and same-as links;
- cleaned paragraph text, a short snippet, and a content hash.

Scripts, styles, navigation, headers, footers, sidebars, forms, cookie/consent banners, advertisements, repeated menu text, and duplicate paragraphs are removed. Paragraph boundaries are retained. Cleaned text has a configurable hard limit. Raw HTML is not persisted.

Content types are deterministic rules based on URL path, title, metadata, JSON-LD type, and official-domain status. No AI classifier is used.

## Display rules

For a domain already identified as the company's official website, the app may store and display bounded cleaned text. Every item shows its source URL, collection time, and “来自公开网页” marker.

A manually entered URL is not silently promoted to an official domain. Third-party pages use `excerpt_only`: title, source, timestamps, metadata, short excerpt, and original link are retained, while the full cleaned body is discarded before storage. PDF items use `metadata_only`; the app records the title/URL and report type but does not download or parse the PDF body in this version.

## Storage

Web Evidence uses a separate user-owned SQLite database:

`%APPDATA%/CompanyDecisionMonitor/web_evidence.sqlite`

It is never added to either bundled symbol index and is never packaged in EXE, Portable ZIP, or Installer artifacts. Tables are:

- `crawl_jobs`;
- `web_evidence`;
- `evidence_links`;
- `crawl_errors`;
- `crawl_metadata`;
- `profile_field_candidates`.

Canonical URL and content hash provide per-company deduplication. The UI can query a company, delete one item, clear one company, or clear all Web Evidence. Cached records have a TTL. Startup runs SQLite `quick_check`; a corrupt file is preserved with a timestamped `.corrupted.*` name before a clean schema is created. Watchlist and the main application database are not touched.

The database contains no raw HTML, cookies, tokens, passwords, account identifiers, or browser profile data.

## Company profile candidates

Official-domain JSON-LD `Organization` fields create traceable `ProfileFieldCandidate` records. A candidate stores the field, proposed/current values, source URL, evidence ID, confidence, and status.

Automatic adoption is limited to a high-confidence official-domain JSON-LD Organization field when the current profile field is empty and there is no conflict. Its `field_sources` entry becomes `official_website_evidence`. Existing or conflicting values remain unchanged and enter `pending`. Descriptions and discovered IR/press URLs are also `pending`; third-party pages are never auto-applied.

## Privacy and exclusions

Web Evidence has no cookie jar, login workflow, CAPTCHA workflow, token input, paywall handling, form submission, POST request, browser-profile import, or user-account storage. It does not send evidence into AI, RAG, training, risk scoring, news counts, or reports.

`xueqiu.com` is a hard-blocked domain. Xueqiu stays a system-browser external link and never enters `WebEvidenceItem`, caching, news, or profile candidates.

## Current limitations

- JavaScript-only pages may expose little useful content through the GET-only pipeline.
- Missing or ambiguous robots.txt is handled conservatively with low-frequency access, but site operators can still block requests.
- PDF bodies are not downloaded or parsed.
- No sitemap ingestion, cross-domain crawl, authenticated content, AI summary, or semantic search is included.
- Public no-key pages can be incomplete, stale, changed, or unavailable; the software does not fabricate missing evidence.
