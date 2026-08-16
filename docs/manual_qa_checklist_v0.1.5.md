# v0.1.5 Web Evidence Final Manual QA Checklist

Release label: `v0.1.5`
Base package version: `0.1.5`
Release type: `Stable Release`

The unchecked administrator-level items below were not executed. They remain useful for post-release issue reproduction, but they must not be interpreted as passed tests.

QA status: `Not manually executed — explicitly waived for v0.1.5 release.`

- Tester:
- Date/time:
- Windows version:
- Installer SHA256: recorded from the final committed build in the release artifacts and GitHub Release.
- Installed path:
- Notes/evidence:

## Maintainer Installer QA Waiver

- Full elevated Installer install/launch/persistence/uninstall QA was not executed by the maintainer.
- This is an explicit release decision, not a passed test.
- Installer confidence is based on:
  - successful Inno Setup build;
  - release artifact validation;
  - frozen EXE self-tests;
  - Portable self-tests;
  - automated dependency/resource validation;
  - sensitive-data scanning.
- Real administrator installation lifecycle remains an unverified residual risk for v0.1.5.
- User-reported installation issues should be tracked after release.

## Administrator installer lifecycle

- [ ] Start `CompanyDecisionMonitor_Setup.exe` and confirm the Windows elevation prompt appears.
- [ ] Complete installation successfully.
- [ ] Confirm the selected installation path is normal and contains the packaged application files.
- [ ] Launch from the Start menu shortcut.
- [ ] If selected during setup, launch from the optional desktop shortcut.
- [ ] Confirm the About page shows `v0.1.5`, base version `0.1.5`, and `Stable Release`.
- [ ] Confirm launch shows no DLL, SQLite, lxml, or Beautiful Soup import error.

## Search and company detail

- [ ] Search `AAPL`.
- [ ] Search `Broadcom`.
- [ ] Search `ASML`.
- [ ] Search `腾讯`.
- [ ] Search `03690`.
- [ ] Search `宁德时代`.
- [ ] Search `300750`.
- [ ] Search two additional randomly selected companies not used in prior manual QA and record them in Notes/evidence.
- [ ] Open and inspect Overview, News, Registry, Sources, and Web Evidence for at least one result.

## Web Evidence

- [ ] Open the AAPL company detail page and the `网页证据` tab.
- [ ] Confirm crawlergo is reported as optional external and that missing crawlergo does not disable the tab.
- [ ] Collect an allowed Apple homepage or Investor Relations URL with at most five pages, depth one, and at least one second between requests.
- [ ] Use `添加 URL` with an explicitly supplied allowed public URL and confirm the same safety/robots flow runs.
- [ ] Confirm title, source, collection time, content type, short excerpt, and original link are visible.
- [ ] Confirm `查看内容` displays source URL, canonical URL, times, cleaned text or the JavaScript-only explanation, headings, and extracted metadata.
- [ ] Confirm `打开原文` opens the public source in the system browser.
- [ ] Confirm allowed official pages may show bounded cleaned text.
- [ ] Confirm third-party pages show only metadata and a short excerpt.
- [ ] Confirm PDF pages show metadata and a link without downloading or parsing the body.
- [ ] Confirm a robots-disallowed page is blocked before content download.
- [ ] Confirm `http://127.0.0.1/` is rejected.
- [ ] Confirm `http://localhost/` is rejected.
- [ ] Confirm `http://169.254.169.254/` is rejected.
- [ ] Confirm `https://xueqiu.com/` and a Xueqiu subdomain cannot start a CrawlJob.
- [ ] Cancel an active crawl and confirm the UI remains responsive.
- [ ] Confirm the cancelled job displays status `cancelled`.
- [ ] Switch to another company while a crawl is running and confirm results remain associated with the original company.
- [ ] Delete one evidence item.
- [ ] Confirm the deleted item is no longer listed.
- [ ] Clear one company's Web Evidence cache.
- [ ] Restart the application and confirm retained evidence persists.
- [ ] Close the application during an active task and confirm shutdown is bounded and leaves no process.

## Search, profile, and watchlist regression

- [ ] Search random unseen ticker, English-name, and Chinese-name companies while a bounded crawl runs.
- [ ] Confirm local search results render without waiting for Web Evidence.
- [ ] Confirm company profile and news loading do not start a crawl.
- [ ] Add and remove a watchlist company.
- [ ] Restart and confirm the watchlist persists.
- [ ] Restart and confirm Web Evidence and settings persist.
- [ ] Confirm the Xueqiu action still opens only in the system browser.

## Shutdown and uninstall

- [ ] Exit the application and confirm no `CompanyDecisionMonitor.exe` process remains.
- [ ] Confirm no `crawlergo.exe` process remains.
- [ ] Confirm no application-started Chrome or Chromium process remains.
- [ ] Uninstall from Windows installed-app management or the installed uninstaller.
- [ ] Confirm installed application files are removed.
- [ ] Confirm Start-menu and optional desktop shortcuts are removed.
- [ ] Confirm no application process remains after uninstall.
- [ ] Confirm AppData retention matches the documented user-data policy and that no unrelated user data was removed.

## Artifact isolation

- [ ] Confirm EXE, Portable ZIP, and Installer contain no `web_evidence.sqlite`.
- [ ] Confirm they contain no crawl history, cleaned page body, raw HTML, crawler cache, reports, browser profile, Cookie, Token, `xq_a_token`, `.env`, AppData, or watchlist.
- [ ] Confirm crawlergo and Chromium binaries are not bundled.
- [ ] Confirm `THIRD_PARTY_NOTICES.md`, Beautiful Soup license, lxml license, and `release_metadata.json` are included.
