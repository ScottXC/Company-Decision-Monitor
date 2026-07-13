# Web Evidence Crawling

Version scope: `v0.1.3-crawlergo-web-evidence`

## Positioning

The Crawlergo Web Evidence Provider is a controlled evidence-collection module for company official websites and user-authorized public pages. It is not a general web crawler, a news full-text collector, an anti-bot bypass tool, a social-media collector, or an AI/RAG ingestion pipeline.

## Allowed Use

- The user opens a company detail page and clicks **采集公司官网公开信息**.
- The user manually enters a company official website, IR page, press page, or authorized public URL.
- The app may suggest the company website from `CompanyProfile.website`, but the user must confirm before crawling.

## Compliance Boundaries

- `robots.txt` is checked before fetching a page.
- Disallowed URLs are skipped and shown in diagnostics.
- Domain request delay is enforced. The default delay is at least one second.
- Maximum pages and maximum depth are enforced.
- The user can cancel an active crawl.
- The app does not bypass login, CAPTCHA, access credentials, paywalls, or risk-control systems.
- The app does not crawl Xueqiu content. Xueqiu remains an external browser handoff only.
- The app does not collect WeChat public account articles, login-only forums, paid news sites, or social-platform body text.
- The app does not send web evidence into AI summary, RAG, training data, or long-term full-text indexing.

## Display Rules

By default the app only stores and displays:

- URL and final URL;
- domain;
- title;
- meta description;
- Open Graph description;
- publication time when available;
- content type classification;
- a short snippet, up to 300 characters;
- extracted text preview, up to 800 characters;
- crawl time;
- robots decision;
- original source link.

The app does not display raw HTML. It does not cache third-party full page text. Full extracted text display is an advanced option and is intended only for pages the user owns or is authorized to inspect.

## Cache Policy

Web evidence cache lives in the user's AppData cache directory. It stores metadata, snippets, URL hash keys, crawl time, and robots decision. It does not enter the installer or portable ZIP. Damaged cache files are ignored safely.

## crawlergo Binary

`crawlergo` is an optional external binary. The app does not bundle it by default. Users can configure the path in Settings. If it is missing, provider status is `dependency_missing` and the crawl button returns a readable message.

## User Responsibility

Users are responsible for entering URLs they are allowed to access. If deeper integration with third-party websites is needed, explicit authorization or official APIs should be obtained first.
