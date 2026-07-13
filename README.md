# Company Decision Monitor

<details open>
<summary><strong>English</strong></summary>

Current version: `v0.1.3`

Current mode: `Open-Source Data Mode`

Release type: `Stable Release`

Company Decision Monitor is a Windows desktop application for company research and corporate activity monitoring. In `Open-Source Data Mode`, normal users do not need to apply for API keys, install Python, run `pip install`, download open-source projects, or import local company files. The installer bundles the runtime dependencies and a generated open-source symbol index for company search, symbol metadata, entity fallback, RSS news fallback, and local watchlist refresh.

The application does not provide investment advice, trading features, buy/sell/order workflows, portfolio P&L, target prices, or return forecasts.

## v0.1.3 Company Data Completeness

This release includes the company-profile completeness work validated during the release-candidate cycle. It focuses on immediate local identity fields, asynchronous visible-detail refresh, confidence-gated Wikidata/GLEIF enrichment, field-level sources, entity-aware coverage, and profile cache schema handling. Public no-key sources are not equivalent to a commercial real-time database: live prices, market capitalization, news, and complete legal records can be absent. Missing fields are never fabricated. AKShare is not bundled in this release.

## Company profile enrichment

Company details now load in stages. The bundled symbol index immediately supplies available security identity, exchange, market, country, currency, sector, industry, and instrument type fields. Wikidata and GLEIF then provide best-effort public entity and legal-entity enrichment in background workers; AKShare can add experimental China/Hong Kong metadata when the optional dependency and its public endpoints are available.

Official website evidence remains user-triggered and robots-compliant. Missing fields are not replaced with fabricated values, zeroes, or generic placeholders. Price and market capitalization remain hidden when no reliable real-time source is enabled. The displayed profile-coverage percentage measures populated supported fields only; it is not an authority or accuracy score.

Diagnostics:

```powershell
python scripts\diagnose_company_profile.py AAPL --local
python scripts\evaluate_profile_coverage.py
```

## v0.1.3 Modern Financial UI

The desktop interface now follows a restrained, modern financial-tool information architecture: search and watchlist are primary, list rows replace card-heavy screens, technical diagnostics are collapsed by default, and company details use focused tabs. Light, dark, and system themes share one tokenized design system and can switch without restarting.

The design borrows general usability principles from modern financial applications. It does not copy Robinhood trademarks, logos, proprietary artwork, iconography, or page layouts. Company Decision Monitor does not provide trading, buy/sell/order, portfolio, P&L, target-price, or return-forecast features.

The local-first search pipeline, SQLite/FTS5 index, debounce, request cancellation, QThreadPool workers, background public enrichment, on-demand news/profile loading, cache, and local watchlist persistence remain unchanged.

## v0.1.3-search-performance-rc1

Search is now local-first and progressive:

- The bundled SQLite symbol index and downloaded Nasdaq cache produce the first results without waiting for public network providers.
- Input is debounced for 350 ms; Enter and the Search button submit immediately.
- Every request has an ID, so a slow response from an older query cannot replace newer results.
- Public no-key providers run concurrently in a background enrichment stage with individual timeouts and a total time budget.
- Company news, full profiles, RSS, and web evidence are not loaded during ordinary company search.
- RapidFuzz only scores a SQL shortlist of at most 200 candidates; it never scans the full 110,000-record universe.
- Recent local searches use a bounded in-memory cache. The first index initialization may be slower, while subsequent searches are normally much faster.

Run the local benchmark with:

```powershell
python scripts\benchmark_search.py
```

See `docs/search_performance.md` for architecture, targets, and limitations.

## Core Workflow

1. Open the desktop application.
2. Go to **Company Search**.
3. Search by company name, ticker, abbreviation, LEI, or registration number.
4. Providers without configured keys are skipped automatically and shown in provider status.
5. Use the default open-source/no-key providers first. Advanced API providers are optional and disabled by default.
6. Add real search results to the local watchlist.
7. Open **Watchlist** to review companies saved on this computer.
8. Open **Company Profile** to inspect provider-returned fields, source metadata, and related news.

## v0.1.3-bundled-open-source-runtime

`v0.1.3-bundled-open-source-runtime` packages the core open-source runtime so ordinary Windows users can install and search immediately.

- Normal users do not need Python, `pip install`, local CSV/Excel/database imports, or third-party API keys.
- Runtime search uses the bundled `symbol_universe.sqlite` index generated from FinanceDatabase equities metadata.
- RapidFuzz and cleanco are bundled as runtime dependencies for fuzzy search and company-name cleaning.
- FinanceDatabase is used at build time to generate the local symbol index; the installed app reads the SQLite index and does not require users to install FinanceDatabase.
- AKShare remains optional/experimental and is not required for the main search workflow.
- Advanced API Providers such as FMP, Alpha Vantage, and Marketaux remain available for advanced users but are disabled by default.
- crawlergo remains an optional external tool because it is GPL-3.0 and should not be bundled unless the project explicitly accepts GPL distribution obligations.

### Bundled open-source components

| Component | Purpose | Bundled | License | Notes |
|---|---|---:|---|---|
| RapidFuzz | Fuzzy matching, alias matching, result ranking, deduplication, news-title similarity | Yes | MIT | Included in the PyInstaller runtime. |
| cleanco | English company-name legal suffix cleaning | Yes | MIT | Used with the existing Chinese suffix cleaner. |
| FinanceDatabase generated symbol index | Global equities symbol universe fallback | Yes, as SQLite index | MIT source package | `symbol_universe.sqlite` is bundled; FinanceDatabase itself is build-time only. |
| AKShare | Experimental China/HK public no-key source | Optional | Not distributed in this package; recheck upstream before bundling | Not required by normal users; may report dependency_missing. |
| crawlergo | Optional user-triggered webpage evidence discovery | No | GPL-3.0 | External binary path only; not bundled, vendored, or used for Xueqiu crawling. |

See `THIRD_PARTY_NOTICES.md` and `third_party/licenses/` for bundled component notices.

## v0.1.3-open-source-search

`v0.1.3-open-source-search` switches the default product direction to `Open-Source Data Mode`.

- Normal users do not need to apply for FMP, Alpha Vantage, Marketaux, Finnhub, NewsAPI, Guardian, OpenCorporates, or other third-party API keys.
- Default search uses no-key/open-source sources: seed alias expansion, FinanceDatabase / Symbol Universe when installed, Nasdaq Symbol Directory, AKShare experimental China/HK provider when installed, Wikidata / Wikipedia, GLEIF, RSS news fallback, and Xueqiu external-link handoff.
- FMP, Alpha Vantage, Marketaux, OpenCorporates, and Companies House remain in code for backward compatibility, but are moved to Advanced API Providers and disabled by default.
- RapidFuzz is used for high-quality fuzzy matching when available, with difflib fallback.
- cleanco is used for English company-name cleaning when available, while the existing Chinese suffix cleaner remains in place.
- FinanceDatabase and AKShare are optional dependencies. If missing, their providers report `dependency_missing` and search continues through other fallbacks.
- Xueqiu remains external link only: no scraping, no unofficial API, no cookie/token, no cache, no indexing, and no AI/RAG ingestion.

Open-source and public no-key providers are best-effort. Coverage, freshness, and accuracy are not equivalent to a commercial financial database.

## v0.1.3-crawlergo-web-evidence

This development module adds **Crawlergo Web Evidence Provider** for controlled company website evidence collection.

- `crawlergo` is optional and is not bundled by default. Configure the binary path in **Settings → 网页证据采集**.
- Crawling is only triggered manually from the company detail page or from a user-entered official/authorized URL.
- The app checks `robots.txt`, applies domain rate limits, enforces maximum pages and maximum depth, and supports user cancellation.
- The app does not bypass login, CAPTCHA, access credentials, paywalls, or risk-control systems.
- The app does not crawl Xueqiu content. Xueqiu remains external-link only.
- The app does not collect WeChat public account articles, login-only forums, paid news sites, or social-platform body text.
- By default, the app stores and displays only metadata, short snippets, text previews, and original links.
- Third-party full page text is not cached, indexed, sent to AI/RAG, or used for training.

## v0.1.3-search-recall-hotfix

`v0.1.3-search-recall-hotfix` fixes P1 search and news recall issues found after the first provider-quality pass.

- Added golden search cases for common English names, U.S. tickers, Hong Kong tickers, A-share tickers, Chinese short names, and common abbreviations.
- Added golden news query cases so company news searches use symbols, company names, legal names, Chinese aliases, and English aliases instead of only one narrow term.
- Improved query expansion for `Apple`, `AAPL`, `腾讯`, `00700`, `阿里巴巴`, `BABA`, `台积电`, `TSM`, `贵州茅台`, `600519`, `BRK.B`, and `BRK-B` style inputs.
- Improved market symbol detection for Hong Kong codes such as `700` / `00700`, A-share codes such as `600519` / `000001`, and U.S. class symbols.
- Improved result ranking so exact symbols and high-confidence seed aliases enter best matches and weak encyclopedia/legal-entity matches stay out of the top group.
- Improved news fallback so symbol-only news searches retry company name and aliases when a provider returns empty results.
- Added developer diagnostics:
  - `python scripts\diagnose_search.py "腾讯"`
  - `python scripts\evaluate_search_quality.py`

Supported search input types include full English company names, Chinese company names, common short names, U.S. tickers, Hong Kong codes, A-share codes, class symbols, LEI-style identifiers, and selected high-confidence abbreviations. Coverage still depends on configured providers and public fallback data; some private companies, low-coverage regions, or weak aliases may still return no result.

## v0.1.3-provider-quality

`v0.1.3-provider-quality` improves the reliability and relevance of the existing `Public + Free API Network Mode` flow without adding a new product surface.

- Better query normalization for whitespace, full-width characters, company suffixes, Hong Kong symbols, A-share symbols, U.S. class symbols such as `BRK.B` / `BRK-B`, and LEI-style identifiers.
- Small high-confidence alias expansion for common names and abbreviations such as Tencent / 腾讯 / HK00700, Alibaba / 阿里巴巴 / BABA / HK09988, TSMC / 台积电 / TSM, BYD / 比亚迪, and Kweichow Moutai / 贵州茅台 / SH600519.
- Improved result ranking so exact symbols, exact names, seed aliases, provider aliases, acronyms, multi-provider hits, and listed-company matches sort more consistently.
- Stable search grouping for best matches, listed companies, legal entities, encyclopedia entities, news, and possible matches.
- Provider health tracking for recent success, failures, rate-limit states, and short automatic backoff after repeated retryable failures.
- More relevant company news ordering with URL/title de-duplication and relevance scoring.
- Stronger company profile merge rules so empty values do not overwrite better fields and field-level provider sources remain visible.
- More reliable watchlist refresh states for single-company and refresh-all flows.
- Cache keys remain stable and redact API keys; corrupted cache files are ignored safely.
- Non-blocking `datetime.utcnow()` deprecation warnings were removed from the public API layer.

## v0.1.2 Stable Release

`v0.1.2` is the core-function stable release. It includes validated real providers, search, company profiles, news, watchlist persistence, cache fallback, API key safety, Xueqiu external handoff, and Windows delivery artifacts:

- Company search aggregation across configured providers and public fallbacks.
- FMP company search, profile mapping, and stock news mapping.
- Alpha Vantage SYMBOL_SEARCH and OVERVIEW mapping.
- Marketaux company news mapping.
- Nasdaq Symbol Directory fallback with cache fallback.
- Wikidata / Wikipedia entity fallback.
- GLEIF legal entity fallback.
- Company profile field merging with field-level provider sources.
- Company news aggregation and de-duplication.
- Local watchlist persistence with single-company and full-list refresh.
- Cache fallback when provider requests fail.
- User-readable provider errors for missing keys, invalid keys, quota/rate limits, network timeouts, parse failures, and empty results.
- Xueqiu external community entry that only opens the system browser and does not scrape, cache, index, or summarize Xueqiu content.
- Release artifact validation, SHA256 generation, real provider smoke testing, user-flow smoke testing, and manual QA checklist.

## UI Guide

The current UI organizes the app into five primary areas: **Dashboard**, **Company Search**, **Watchlist**, **Company Profile**, and **Data Source Settings**.

### Dashboard

- Use the top search entry to search company names, tickers, abbreviations, or short names.
- The dashboard shows only high-level operational status: search capability, optional advanced API count, watchlist count, and cache status.
- If the watchlist is empty, use the search action to add a company.
- The app does not show fake trending companies when there is no reliable public source.

### Company Search

- Search by full company name, ticker, abbreviation, LEI, or registration number.
- Results are grouped into best matches, listed securities, legal entities, related news, and possible matches.
- Each result card shows only essential fields first; provider details are kept out of the main flow.
- Local provider errors and unconfigured providers are summarized instead of taking over the page.

### Advanced API Provider Configuration

- Normal users can skip this section.
- Open **Settings** -> **Advanced API Providers** only if you explicitly want legacy API-backed coverage.
- Optional legacy sources include FMP, Alpha Vantage, and Marketaux.
- Empty input fields do not overwrite existing keys.
- Saved keys are stored locally and displayed only as masked values.

### Provider Status

- The dashboard shows provider categories in plain language.
- The settings page shows detailed provider status and connectivity testing.
- Status labels include available, not configured, not connected, error, rate limited, invalid key, and empty result.

### Watchlist

- Click **Add to Watchlist** from a search result.
- Watchlist data is stored locally in the user AppData directory.
- Removing a company from the watchlist does not clear cache or historical search data.

### Cache

- Open **Settings** -> **Cache & Privacy**.
- Use **Clear Cache** to remove public request cache files.
- Cache is only used to reduce repeated provider requests and does not contain plaintext API keys.

## Data Source Principles

- No fake company data.
- No fake news.
- No fake financial data.
- No CSV, Excel, or local company database import flow.
- No hardcoded real API keys.
- User API keys are not packaged into the installer.
- API keys are stored only on the user's computer.
- The UI displays masked keys only.
- Network and provider failures should show readable status instead of a blank screen.

## Provider Matrix

| Provider | Coverage | Purpose | API key required | Current status |
|---|---|---|---|---|
| GLEIF LEI | Global legal entities | LEI, legal name, registration status, jurisdiction | No | Implemented |
| Nasdaq Symbol Directory | U.S. listed securities | Symbol and security name search | No | Implemented |
| Financial Modeling Prep | Global listed companies | Symbol search, profile, news | Yes, optional free key | Search/profile/news mapping implemented |
| Alpha Vantage | Major listed securities | Symbol search, overview | Yes, optional free key | SYMBOL_SEARCH/OVERVIEW mapping implemented |
| Marketaux | Financial news | News and media mentions | Yes, optional free key | News mapping implemented |
| Xueqiu Community Entry | External community link | Manual browser handoff to Xueqiu stock pages | No | External link only; no scraping or cache |
| OpenCorporates | Company registries | Company search and jurisdiction metadata | Yes, plan-dependent | Basic mapping implemented |
| UK Companies House | UK companies | Company search and status | Yes | Basic mapping implemented |
| Norway BRREG | Norwegian companies | Organization number, legal name, address | No | Basic mapping implemented |
| Wikidata / Wikipedia | Public entity data | Entity label, aliases, description, Wikipedia URL | No | Fallback implemented |
| INSEE SIRENE | French companies | SIREN/SIRET and legal units | Possibly | Stub |
| ABN Lookup | Australian businesses | ABN, business name, status | Yes | Stub |
| Japan Corporate Number | Japanese entities | Corporate number, name, address | Yes | Stub |
| Singapore ACRA Open Data | Singapore entities | UEN, entity name, status | Usually no key or optional | Stub |
| Corporations Canada | Canadian federal corporations | Corporation number and profile | Public plan key | Stub |
| Guardian Open Platform | News | News supplement | Yes | Stub |
| NewsAPI | News aggregation | News supplement | Yes | Stub |
| RSS / Atom | User-configured public feeds | News fallback | No | Future/stub |

## Region Coverage Strategy

- United States: Nasdaq Symbol Directory, FMP, Alpha Vantage, GLEIF, Marketaux/RSS.
- United Kingdom: Companies House, OpenCorporates, GLEIF, Marketaux/RSS.
- France and Europe: GLEIF, OpenCorporates, FMP, Marketaux/RSS; INSEE SIRENE remains a stub.
- Canada: Corporations Canada remains a stub; fallback sources are GLEIF, OpenCorporates, Marketaux/RSS.
- Australia: ABN Lookup remains a stub; fallback sources are GLEIF, OpenCorporates, Marketaux/RSS.
- Japan: Corporate Number remains a stub; fallback sources are GLEIF, OpenCorporates, Marketaux/RSS.
- Singapore: ACRA/data.gov.sg remains a stub; fallback sources are GLEIF and Marketaux/RSS.
- Norway: BRREG, GLEIF, OpenCorporates, Marketaux/RSS.
- Complex regions such as China, India, Brazil, and Germany are not handled through fragile website scraping or login-protected pages.

## API Key Storage

API keys are stored at:

```text
%APPDATA%\CompanyDecisionMonitor\api_keys.json
```

They are stored only on the local machine. Logs and cache keys do not include plaintext keys. The installer does not include user keys, cache files, watchlist data, or `.env`.

## Configure Optional Advanced API Providers

Normal users do not need these keys. Advanced users can explicitly enable legacy API providers in Settings:

- FMP: <https://site.financialmodelingprep.com/register>
- Alpha Vantage: <https://www.alphavantage.co/support/#api-key>
- Marketaux: <https://www.marketaux.com/register>

The app still works with public fallbacks when these keys are missing, but coverage is narrower.

## Xueqiu Community Entry

The app supports opening a related Xueqiu stock page from the company profile when a supported stock symbol can be mapped to a Xueqiu URL. Xueqiu is currently treated only as an external community entry point.

- The app opens Xueqiu pages in the user's system browser after a manual click.
- The app does not scrape Xueqiu webpages.
- The app does not call non-public Xueqiu interfaces.
- The app does not use user cookies or tokens.
- The app does not cache, index, copy, transfer, or store Xueqiu content.
- The app does not use Xueqiu content for AI summaries, training, RAG, or local corpora.
- The app does not display Xueqiu posts, comments, body text, or user speech.
- Deeper Xueqiu content integration should only be considered with explicit Xueqiu authorization or an official partnership/API.

普通用户可以在公司详情页点击“打开雪球”，由系统浏览器自行打开雪球页面查看。该入口仅用于手动跳转，不是新闻抓取源。

## Run

Development mode:

```bat
run_dev.bat
```

Run the built executable:

```bat
dist\CompanyDecisionMonitor\CompanyDecisionMonitor.exe
```

SQLite packaging self-test:

```bat
dist\CompanyDecisionMonitor\CompanyDecisionMonitor.exe --self-test sqlite
```

If the packaged app shows `DLL load failed while importing _sqlite3`, the Windows package is missing the SQLite runtime DLL. Download or rebuild the hotfix package; current builds run the SQLite self-test during packaging and release validation.

## Test

```bat
ruff check src tests scripts
pytest
python -m compileall src scripts
```

Tests do not call external APIs. They use local mappings and mocked responses.

## Release Validation

Standard checks:

```bat
ruff check src tests scripts
pytest
python -m compileall src scripts
build.bat
python scripts\validate_release_artifacts.py
python scripts\hash_release_artifacts.py
```

Manual real-provider smoke test:

```bat
python scripts\smoke_real_providers.py
```

This script performs a small number of real public/provider requests. It reads keys from the user's AppData config, environment variables, or a local untracked `.env` file. It skips unconfigured keyed providers, masks keys in output, and writes `reports\smoke_provider_report.json`.

Service-layer user-flow smoke test:

```bat
python scripts\smoke_user_flow.py
```

This script uses a temporary local data directory, searches `Apple`, `AAPL`, and `IBM`, loads a best-result profile/news flow, adds/removes a temporary watchlist item, and writes `reports\smoke_user_flow_report.json`.

Release artifact validation:

```bat
python scripts\validate_release_artifacts.py
```

This verifies the exe, portable zip, installer, portable zip contents, installer script references, and sensitive markers. It writes `reports\release_artifact_report.json`.

SHA256 generation:

```bat
python scripts\hash_release_artifacts.py
```

This writes `reports\release_hashes.json` and prints Markdown-ready hashes for GitHub Release notes.

The normal pytest suite does not make real network calls. Only `smoke_real_providers.py` and `smoke_user_flow.py` may contact external providers when run manually.

## Build And Package

```bat
build.bat
```

Build outputs:

- `dist\CompanyDecisionMonitor\CompanyDecisionMonitor.exe`
- `dist\CompanyDecisionMonitor_Portable.zip`
- `dist\installer\CompanyDecisionMonitor_Setup.exe`

The installer should not contain `.env`, user API keys, cache directories, watchlist data, tests, source directories, `.git`, or `node_modules`.

## Not Implemented Yet

- Full financial modeling.
- Full risk rule engine.
- AI summaries.
- Research report export.
- Full request mapping for Guardian, NewsAPI, INSEE, ABN, Japan NTA, Singapore ACRA, and Canada providers.
- Deep official registry integration for complex regions such as China, India, Brazil, and Germany.

## Feedback / Issues

Please report bugs, provider problems, installation issues, and feature requests through [GitHub Issues](https://github.com/ScottXC/Company-Decision-Monitor/issues).

- Use **Bug report** for crashes, launch failures, installer problems, or broken app flows.
- Use **Provider issue** for API key, quota, rate limit, provider mapping, search, news, or cache fallback problems.
- Use **Feature request** for future product ideas or data source suggestions.
- Do not paste full API keys, `.env` files, AppData key storage, cache files, watchlist files, cookies, tokens, or full request URLs containing credentials.
- See [post-release feedback guidance](docs/post_release_feedback.md) before sharing logs or screenshots.

## Notes

- Free-tier limits, fields, registration flows, and terms may change. Always refer to the official provider pages.
- Search results come from external providers and should be verified against original sources.
- This software does not constitute investment advice.

</details>

<details>
<summary><strong>中文</strong></summary>

当前版本：`v0.1.3`
当前模式：`Open-Source Data Mode`

Company Decision Monitor 是面向普通用户的公司研究与企业动态监控 Windows 桌面软件。当前版本默认不要求普通用户申请任何 API key，不要求安装 Python，不要求手动 `pip install`，也不要求导入 Excel、CSV 或本地公司数据库；安装包会内置运行依赖和开源 symbol universe 索引。

本软件不提供投资建议，不提供交易、买入、卖出、下单、组合收益或目标价功能。

## v0.1.3 公司资料完整度

本正式版包含经过发布候选验证的公司资料完整度改进，重点包括本地身份字段即时展示、异步资料回填后刷新可见详情、Wikidata/GLEIF 高置信补全、字段级来源、按实体类型计算完整度和 Profile 缓存 schema。公开无 key 来源不等同于商业实时数据库，价格、市值、新闻和完整法人资料可能缺失；系统不会伪造缺失字段。本版本不内置 AKShare。

## 公司资料补全机制

公司详情采用分阶段加载。内置证券索引会立即提供其真实包含的公司名称、代码、交易所、市场、国家、币种、板块、行业和证券类型；Wikidata 与 GLEIF 在后台补充公开实体和法人资料；AKShare 安装且公开接口可用时，可实验性补充中国 A 股和港股资料。

官网资料仍需用户主动触发，并遵守 robots.txt。没有可靠来源的字段不会使用假数据、0 或通用占位值补齐；没有可靠实时来源时，价格和市值会被隐藏。资料完整度只表示当前支持字段的填充比例，不代表权威性或准确性。

```powershell
python scripts\diagnose_company_profile.py AAPL --local
python scripts\evaluate_profile_coverage.py
```

## v0.1.3 现代金融工具 UI

桌面界面现采用克制、现代的金融工具信息架构：搜索和自选优先，以列表行替代卡片堆叠，技术诊断默认折叠，公司详情按页签聚焦展示。浅色、深色和跟随系统主题共用统一设计 token，可即时切换，无需重启。

本次仅借鉴现代金融应用的通用可用性原则，不复制 Robinhood 商标、Logo、专有插图、图标或页面布局。软件不提供交易、买入、卖出、下单、持仓、收益、目标价或回报预测功能。

本地优先搜索、SQLite/FTS5、debounce、request id、QThreadPool、后台公开数据增强、详情和新闻按需加载、缓存与本地自选持久化保持不变。

## v0.1.3-search-performance-rc1

搜索现已改为本地优先、渐进补充：

- 首批结果只查询内置 SQLite 开源证券索引和已下载的 Nasdaq 本地缓存，不等待公网 provider。
- 输入停止 350 ms 后触发搜索；按 Enter 或点击搜索按钮会立即提交。
- 每次搜索使用 request id，旧查询即使稍后返回也不会覆盖新查询。
- Wikidata、GLEIF、AKShare 等公开来源在后台有限并发补充，并受单 provider timeout 和总时间预算限制。
- 普通搜索阶段不加载新闻、完整公司详情、RSS 或网页证据；这些内容只在公司详情页按需异步加载。
- RapidFuzz 只对 SQLite 筛出的最多 200 条候选评分，不再扫描 11 万条全量索引。
- 最近查询使用有界内存缓存。首次索引初始化可能稍慢，后续搜索通常会明显加快。

运行本地性能基准：

```powershell
python scripts\benchmark_search.py
```

架构、性能门槛和限制见 `docs/search_performance.md`。

## 核心流程

1. 打开软件。
2. 进入「公司搜索」。
3. 输入公司名称、股票代码、简称、LEI 或注册号。
4. 未配置 key 的 provider 会自动跳过并显示状态。
5. 默认无需配置 API key；高级用户可在设置中显式启用 Advanced API Providers。
6. 从真实搜索结果点击「添加自选」。
7. 在「自选公司」集中查看本机保存的公司。
8. 在「公司详情」查看 provider 返回的基础信息、来源和相关新闻。

## v0.1.3-bundled-open-source-runtime

本版本把核心开源运行组件和必要 symbol index 随 Windows 安装包/便携包分发：

- 普通用户安装后即可搜索公司，不需要 API key、Python 环境、pip install 或本地数据文件。
- 运行时默认读取内置 `symbol_universe.sqlite`，该索引由 FinanceDatabase equities metadata 在构建阶段生成。
- RapidFuzz 和 cleanco 随 PyInstaller runtime 打包，用于 fuzzy search、别名匹配、去重和公司名清洗。
- FinanceDatabase 仅作为构建阶段数据来源；已安装软件不会要求用户安装 FinanceDatabase。
- AKShare 仍为 optional / experimental，不阻塞主搜索。
- FMP / Alpha Vantage / Marketaux 等 Advanced API Providers 默认关闭，只供高级用户显式启用。
- crawlergo 仍是 optional external tool，不随安装包内置；原因是 GPL-3.0 分发合规和可选外部工具定位。

| 组件 | 用途 | 是否内置 | License | 说明 |
|---|---|---:|---|---|
| RapidFuzz | 模糊搜索、别名匹配、排序、去重 | 是 | MIT | PyInstaller runtime 内置。 |
| cleanco | 英文公司名后缀清理 | 是 | MIT | 与内置中文后缀清理规则配合使用。 |
| FinanceDatabase 生成的 symbol index | 全球 equities symbol universe fallback | 是，SQLite 索引 | MIT source package | 只用于搜索召回，不是实时行情源。 |
| AKShare | 中国 A 股/港股 experimental public source | 可选 | 本安装包不分发；正式内置前需复核上游许可证 | 默认不阻塞主流程。 |
| crawlergo | 手动网页证据发现 | 否 | GPL-3.0 | 外部路径配置，不内置、不抓取雪球。 |

详见 `THIRD_PARTY_NOTICES.md` 和 `third_party/licenses/`。

## v0.1.3-open-source-search

本版本将默认产品模式切换为 `Open-Source Data Mode`：

- 普通用户默认不需要申请 FMP、Alpha Vantage、Marketaux、Finnhub、NewsAPI、Guardian、OpenCorporates 等第三方 API key。
- 默认搜索来源调整为：seed aliases / query expansion、FinanceDatabase / Symbol Universe（如已安装）、Nasdaq Symbol Directory、AKShare experimental（如已安装）、Wikidata / Wikipedia、GLEIF、RSS News fallback、雪球外部链接入口。
- FMP / Alpha Vantage / Marketaux / OpenCorporates / Companies House 代码保留，但移入 Advanced API Providers，默认关闭。
- RapidFuzz 用于增强 fuzzy matching；不可用时回退到 difflib。
- cleanco 用于英文公司名清理；中文公司后缀继续使用内置规则。
- FinanceDatabase 和 AKShare 作为 optional dependency；未安装时 provider 显示 `dependency_missing`，不会阻塞主搜索流程。
- 雪球仍然只是外部链接入口，不抓取、不缓存、不索引、不使用雪球登录凭据或访问令牌。

开源和公开无 key 数据源是 best-effort，不等同于商业金融数据库；覆盖范围、实时性和准确性会受公开来源限制。

## v0.1.3-crawlergo-web-evidence

本开发模块新增「网页证据采集」，用于在公司详情页手动采集公司官网或授权公开页面的网页证据。

- `crawlergo` 是可选外部二进制文件，默认不随安装包打包；可在「设置 → 网页证据采集」配置路径。
- 采集只能由用户在公司详情页点击触发，或由用户手动输入官网 / IR / 授权公开 URL 触发。
- 采集前检查 `robots.txt`，支持域名限速、最大页数、最大深度和用户取消。
- 不绕过登录、验证码、登录凭据、访问令牌、付费墙或风控限制。
- 雪球仍然只是外部链接入口，不采集雪球内容。
- 不采集微信公众号、需要登录的论坛、付费新闻站或社交平台正文。
- 默认只保存和展示元数据、短摘录、文本预览和原文链接。
- 不缓存第三方网页全文，不进入 AI/RAG，不用于训练数据。

## v0.1.3-search-recall-hotfix

本版本暂停 rc 发布流程，优先修复用户反馈的“搜不到目标公司和相关新闻”问题：

- 新增搜索质量 golden cases，覆盖英文公司名、美股代码、港股代码、A 股代码、中文简称和常见缩写。
- 新增新闻查询 golden cases，确保新闻搜索同时使用股票代码、公司名、法定名、中文别名和英文别名。
- 增强 `Apple`、`AAPL`、`腾讯`、`00700`、`阿里巴巴`、`BABA`、`台积电`、`TSM`、`贵州茅台`、`600519`、`BRK.B`、`BRK-B` 等输入的 query expansion。
- 增强港股代码、A 股代码和美股 class symbol 识别。
- 改进排序：精确代码和高置信别名进入最佳匹配，弱百科/法人实体结果不会压过明确证券结果。
- 改进新闻 fallback：按代码无结果时自动尝试公司名和别名。
- 新增诊断命令：
  - `python scripts\diagnose_search.py "腾讯"`
  - `python scripts\evaluate_search_quality.py`

当前支持英文公司名、中文公司名、简称、美股代码、港股代码、A 股代码、class symbol、LEI 样式标识和少量高置信缩写。搜索覆盖仍受免费 provider、公开 fallback 和地区数据可得性限制；部分私营公司、低覆盖地区或弱别名仍可能无结果。

## v0.1.3-provider-quality

本版本不新增大功能，重点提升 v0.1.2 已有 provider 和搜索闭环的质量：

- 增强搜索规范化：空格、全角半角、公司后缀、港股代码、A 股代码、`BRK.B` / `BRK-B`、LEI 风格标识。
- 增强中文、简称和缩写识别：腾讯、阿里巴巴、台积电、比亚迪、贵州茅台、中国平安、HSBC、TSMC、BYD 等高置信别名只用于 query expansion，不作为本地公司数据返回。
- 改进排序：代码完全匹配、名称完全匹配、seed alias、provider alias、缩写、多 provider 命中和上市公司结果会更靠前。
- 改进分组：最佳匹配、上市公司、法人实体、百科实体、新闻和可能相关结果分组更稳定。
- 增强 provider health：记录最近成功、最近错误、连续失败和短暂 backoff；手动测试连接不受 backoff 影响。
- 增强新闻相关性：按标题/摘要命中、财经来源、发布时间和 provider 优先级排序，并减少重复新闻。
- 增强公司详情合并：空值不会覆盖高质量字段，字段来源继续保留。
- 增强自选刷新：单项刷新、全部刷新、失败、缓存来源和刷新时间状态更清楚。
- 增强缓存：cache key 不含明文 API key，损坏缓存会被安全忽略，清理缓存继续真实删除本地缓存。
- 清理非阻塞 warning：public API 层不再使用 `datetime.utcnow()`。

## v0.1.2

本版本重点跑通 Public + Free API Network Mode 闭环：

- 公司搜索聚合。
- FMP 公司搜索、profile 映射和股票新闻映射。
- Alpha Vantage SYMBOL_SEARCH 和 OVERVIEW 映射。
- Marketaux 新闻映射。
- Nasdaq Symbol Directory fallback 和缓存 fallback。
- Wikidata / Wikipedia 实体 fallback。
- GLEIF 法人实体 fallback。
- 公司详情字段合并，并记录字段来源。
- 新闻聚合和去重。
- 自选公司本地持久化、单个刷新和全部刷新。
- provider 请求失败时使用缓存 fallback。
- 缺 key、key 无效、额度限制、限流、网络超时、解析失败和空结果会显示可读错误。

## UI 使用说明

当前 UI 将主流程收敛为「首页」「搜索公司」「自选公司」「公司详情」「设置」五个入口。

### 首页怎么用

- 在首页顶部输入公司名称、股票代码、简称或缩写，点击「搜索公司」进入联网搜索。
- 首页只展示关键状态：搜索能力、可选高级 API 数量、自选公司数量和缓存状态。
- 自选预览为空时，点击「去搜索公司」开始添加。
- 热门公司目前不显示无可靠来源的榜单，避免展示伪造数据。

### 搜索页怎么用

- 输入公司全称、股票代码、简称、缩写、LEI 或注册号后点击「搜索」。
- 结果会按「最佳匹配」「上市公司」「法人实体」「相关新闻」「可能相关」组织。
- 每条公司结果只显示核心字段；更多字段在「更多字段」折叠区查看。
- 局部 provider 错误和未配置项会收进「数据源诊断」，不会挤占主要搜索结果。

### 如何配置 Advanced API Providers

普通用户无需配置。高级用户如需扩展覆盖，可打开「设置」→「Advanced API Providers」：

- 显式启用 Advanced API Providers。
- 可选来源包括 FMP、Alpha Vantage、Marketaux 等 legacy provider。
- 输入框留空不会覆盖已有 key；保存后界面只显示 masked key。
- 输入框为空不会覆盖已有 key；界面只显示 masked key。

### 如何判断 provider 状态

- 首页只显示大类状态：核心搜索源、公司信息源、新闻源、公开补充源。
- 设置页「数据源总览」显示 provider 状态表。
- 设置页「公开数据源」显示无需 key 的 provider。
- 状态含义：可用、未配置、暂未接入、异常、限流、Key 可能无效、无结果。

### 如何添加自选公司

- 在搜索结果中点击「添加自选」。
- 自选公司保存在用户本机 AppData，不会打包进安装包。
- 打开「自选公司」可筛选、查看详情或删除自选。
- 删除自选不会清理缓存或历史搜索结果。

### 如何清理缓存

- 打开「设置」→「缓存与隐私」。
- 点击「清理缓存」删除公开请求缓存。
- 缓存只用于减少公开数据源请求次数，不包含明文 API key。

### 为什么某些数据源未配置也能搜索

部分 provider 不需要 key，例如 GLEIF、Nasdaq Symbol Directory、Norway BRREG。需要 key 的增强 provider 未配置时会自动跳过，不会阻塞其他来源。

### 为什么有些国家 provider 是 optional 或 stub

不同国家注册数据源的认证、字段、限流和服务条款差异较大。v0.1.2 只接入已完成基础映射的来源，其他来源保留为 registry/stub，以免展示不稳定或不可复现的数据。

## 数据源原则

- 不伪造公司数据。
- 不伪造新闻。
- 不伪造财务数据。
- 不做 CSV / Excel / 本地公司数据库导入。
- 不硬编码任何真实 API key。
- 不把用户 API key 打进安装包。
- API key 只保存在用户本机 AppData 目录。
- UI 只显示 masked key。
- 网络失败会显示 provider 级错误，不应导致白屏。

## 搜索 API Matrix

| Provider | 覆盖范围 | 用途 | 是否需要 API key | 是否免费 | 官方注册 / 获取入口 | 当前实现状态 | 备注 |
|---|---|---|---|---|---|---|---|
| GLEIF LEI | 全球 LEI 法人实体 | LEI、法人名称、注册状态、司法辖区 | 否 | 是 | https://www.gleif.org/en/lei-data/gleif-api | 已实现 | 不代表股票行情 |
| Nasdaq Symbol Directory | 美国上市证券目录 | symbol / security name 搜索 | 否 | 是 | https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs | 已实现 | 公共文件 fallback |
| Financial Modeling Prep | 全球上市公司 | symbol search、profile、新闻 | 是：`FMP_API_KEY` | 免费层，以官方为准 | https://site.financialmodelingprep.com/register | 已实现搜索/profile/新闻映射 | 免费层限制可能变化 |
| Alpha Vantage | 全球主流上市证券 | SYMBOL_SEARCH、OVERVIEW | 是：`ALPHA_VANTAGE_API_KEY` | 免费层，以官方为准 | https://www.alphavantage.co/support/#api-key | 已实现 SYMBOL_SEARCH/OVERVIEW 映射 | 免费频率限制较严格 |
| Marketaux | 全球财经新闻 | 新闻、媒体提及 | 是：`MARKETAUX_API_KEY` | 免费层，以官方为准 | https://www.marketaux.com/register | 已实现新闻映射 | 不复制新闻全文 |
| OpenCorporates | 140+ jurisdictions 注册企业 | company search、jurisdiction、company number | 是：`OPENCORPORATES_API_TOKEN` | 以官方计划为准 | https://api.opencorporates.com/documentation/API-Reference | 已实现基础搜索映射 | 可能需要资格或付费计划 |
| UK Companies House | 英国公司注册信息 | company search、company number、status | 是：`COMPANIES_HOUSE_API_KEY` | 公共 API 免费但需认证 | https://developer.company-information.service.gov.uk/get-started | 已实现基础搜索映射 | 未配置时自动跳过 |
| Norway BRREG | 挪威企业注册 | organization number、legal name、address | 否 | 是 | https://data.brreg.no/enhetsregisteret/api/dokumentasjon/en/index.html | 已实现基础搜索映射 | 国家注册 fallback |
| Wikidata / Wikipedia | 公开百科实体 | label、aliases、description、Wikipedia URL | 否 | 是 | https://www.wikidata.org/wiki/Wikidata:Data_access | 已实现 fallback | 不作为财务权威来源 |
| INSEE SIRENE | 法国企业注册 | SIREN/SIRET、legal unit | 可能需要 token | 以官方为准 | https://portail-api.insee.fr/ | Stub | 认证规则复杂 |
| Australia ABN Lookup | 澳大利亚企业 | ABN、business name、status | 是：`ABN_LOOKUP_GUID` | 官方 GUID | https://abr.business.gov.au/Documentation/WebServiceRegistration | Stub | 后续接入 |
| Japan Corporate Number | 日本法人番号 | corporate number、name、address | 是：`JAPAN_CORPORATE_NUMBER_APP_ID` | 免费申请 | https://www.houjin-bangou.nta.go.jp/webapi/index.html | Stub | 后续接入 |
| Singapore ACRA Open Data | 新加坡企业 | UEN、entity name、status | 通常无 key 或可选 | 公共数据 | https://data.gov.sg/dataset/acra-information-on-corporate-entities | Stub | 后续可缓存公开数据集 |
| Corporations Canada | 加拿大联邦公司 | corporation number、profile | 需要 Public Plan key | 以官方为准 | https://api.ised-isde.canada.ca/en/docs?api=corporations | Stub | 需官方订阅 |
| Guardian Open Platform | Guardian 新闻 | 新闻补充源 | 是：`GUARDIAN_API_KEY` | 免费 key，按官方条款 | https://open-platform.theguardian.com/access/ | Stub | 后续接入 |
| NewsAPI | 新闻聚合 | 新闻补充源 | 是：`NEWSAPI_API_KEY` | 免费层限制严格 | https://newsapi.org/register | Stub | 后续接入 |
| RSS / Atom | 用户配置公开 RSS | 新闻 fallback | 否 | 是 | https://www.rssboard.org/rss-specification | Stub/未来扩展 | 不抓取搜索引擎页面 |

## 国家和地区覆盖策略

- 美国：Nasdaq Symbol Directory、FMP、Alpha Vantage、GLEIF、Marketaux/RSS。
- 英国：Companies House、OpenCorporates、GLEIF、Marketaux/RSS。
- 法国/欧洲：GLEIF、OpenCorporates、FMP、Marketaux/RSS，INSEE SIRENE 仍为 stub。
- 加拿大：Corporations Canada 仍为 stub；通用回退为 GLEIF、OpenCorporates、Marketaux/RSS。
- 澳大利亚：ABN Lookup 仍为 stub；通用回退为 GLEIF、OpenCorporates、Marketaux/RSS。
- 日本：Corporate Number 仍为 stub；通用回退为 GLEIF、OpenCorporates、Marketaux/RSS。
- 新加坡：ACRA/data.gov.sg 仍为 stub；通用回退为 GLEIF、Marketaux/RSS。
- 挪威：BRREG、GLEIF、OpenCorporates、Marketaux/RSS。
- 中国、印度、巴西、德国等复杂地区：不做网页 DOM 抓取，不绕过登录、验证码或反爬；通过 GLEIF、OpenCorporates、金融 provider 和新闻源作为 fallback，并在 UI 中明确覆盖限制。

## Advanced API Provider 配置方式

普通用户默认不需要执行本节。

1. 打开「设置」。
2. 进入「Advanced API Providers」。
3. 显式启用高级 provider。
4. 填写对应 key 并保存。
5. 返回「公司搜索」执行查询。

Key 存储方式：

- 存储位置：`%APPDATA%\CompanyDecisionMonitor\api_keys.json`
- 只保存在用户本机。
- UI 显示 masked key。
- 日志和缓存 key 不包含明文 key。
- 安装包不包含用户 key、缓存、自选公司或 `.env`。

可选 Advanced API Provider 注册入口：

- FMP：<https://site.financialmodelingprep.com/register>
- Alpha Vantage：<https://www.alphavantage.co/support/#api-key>
- Marketaux：<https://www.marketaux.com/register>

## 本地缓存

缓存用于减少公开 API 请求次数和改善体验。缓存位于 AppData 的 `cache/public_api/`，不写入源码目录，不打包进安装包。设置页可以清理缓存。

## 运行方式

开发运行：

```bat
run_dev.bat
```

直接运行已构建 exe：

```bat
dist\CompanyDecisionMonitor\CompanyDecisionMonitor.exe
```

## 测试

```bat
ruff check src tests scripts
pytest
python -m compileall src scripts
```

测试不真实调用外部 API，使用本地映射和假响应。

## 构建与打包

```bat
build.bat
```

构建产物：

- `dist\CompanyDecisionMonitor\CompanyDecisionMonitor.exe`
- `dist\CompanyDecisionMonitor_Portable.zip`
- `dist\installer\CompanyDecisionMonitor_Setup.exe`

安装包不应包含 `.env`、用户 API key、缓存目录、自选公司、测试目录、源码目录、`.git` 或 `node_modules`。

## 当前未实现

- 完整财务建模。
- 完整风险规则引擎。
- AI 总结。
- 导出研究报告。
- Guardian / NewsAPI / INSEE / ABN / Japan NTA / Singapore ACRA / Canada 等 provider 的完整请求映射。
- 中国、印度、巴西、德国等复杂地区的官方注册 API 深度接入。

## Feedback / Issues

请通过 [GitHub Issues](https://github.com/ScottXC/Company-Decision-Monitor/issues) 反馈 bug、provider 问题、安装问题和功能建议。

- 启动失败、安装失败、崩溃或主流程异常，请使用 **Bug report**。
- API key、额度、限流、provider 映射、搜索、新闻或缓存 fallback 问题，请使用 **Provider issue**。
- 新功能或新数据源建议，请使用 **Feature request**。
- 不要提交完整 API key、`.env`、AppData key 文件、缓存文件、自选文件、cookie、token 或包含凭据的完整请求 URL。
- 提交日志或截图前，请先查看 [发布后反馈说明](docs/post_release_feedback.md)。

## 注意事项

- 免费层额度、字段覆盖、注册流程和服务条款可能变化，请以 provider 官方页面为准。
- 搜索结果来自外部 provider，用户需要核验原始来源。
- 本软件不构成投资建议。

</details>
