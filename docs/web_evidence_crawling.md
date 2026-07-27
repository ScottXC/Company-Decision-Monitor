# Web Evidence Crawling (legacy note)

This file described the early `v0.1.3-crawlergo-web-evidence` prototype. The current implementation and safety decisions are documented in [web_evidence.md](web_evidence.md).

The v0.1.5 implementation replaces the prototype JSON cache and direct crawlergo invocation with an independent AppData SQLite store, redirect-aware SSRF validation, mandatory robots policy, a cancellable GET-only collection service, official/third-party display rules, and traceable profile candidates. Crawlergo and Chromium remain unbundled; crawlergo is detected only as an optional external diagnostic runtime in this release.
