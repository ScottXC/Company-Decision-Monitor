# Company Decision Monitor

Current version: `v0.1.1`

Current mode: `Public + Free API Network Mode`

Company Decision Monitor is a Windows desktop application for company research and corporate activity monitoring. It helps users search public company and entity data, review provider-backed company profiles, track a local watchlist, and inspect publicly available news or market-related signals where configured data sources support them.

The application does not provide investment advice, trading features, buy/sell/order workflows, portfolio P&L, target prices, or return forecasts.

## Core Workflow

1. Open the desktop application.
2. Go to **Company Search**.
3. Search by company name, ticker, abbreviation, LEI, or registration number.
4. Providers without configured keys are skipped automatically and shown in provider status.
5. Configure optional free API keys to improve company search, profile, and news coverage.
6. Add real search results to the local watchlist.
7. Open **Watchlist** to review companies saved on this computer.
8. Open **Company Profile** to inspect provider-returned fields, source metadata, and related news.

## UI Guide

v0.1.1 UI Polish organizes the app into five primary areas: **Dashboard**, **Company Search**, **Watchlist**, **Company Profile**, and **Data Source Settings**.

### Dashboard

- Use the top search entry to search company names, tickers, abbreviations, or short names.
- The dashboard shows only high-level operational status: search capability, configured free API key count, watchlist count, and cache status.
- If the watchlist is empty, use the search action to add a company.
- The app does not show fake trending companies when there is no reliable public source.

### Company Search

- Search by full company name, ticker, abbreviation, LEI, or registration number.
- Results are grouped into best matches, listed securities, legal entities, related news, and possible matches.
- Each result card shows only essential fields first; provider details are kept out of the main flow.
- Local provider errors and unconfigured providers are summarized instead of taking over the page.

### Free API Key Configuration

- Open **Settings** -> **Free API key**.
- Recommended optional sources include FMP, Alpha Vantage, and Marketaux.
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
| Financial Modeling Prep | Global listed companies | Symbol search, profile, news | Yes, optional free key | Basic mapping implemented |
| Alpha Vantage | Major listed securities | Symbol search, overview | Yes, optional free key | Symbol search mapping implemented |
| Marketaux | Financial news | News and media mentions | Yes, optional free key | News mapping implemented |
| OpenCorporates | Company registries | Company search and jurisdiction metadata | Yes, plan-dependent | Basic mapping implemented |
| UK Companies House | UK companies | Company search and status | Yes | Basic mapping implemented |
| Norway BRREG | Norwegian companies | Organization number, legal name, address | No | Basic mapping implemented |
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

## Run

Development mode:

```bat
run_dev.bat
```

Run the built executable:

```bat
dist\CompanyDecisionMonitor\CompanyDecisionMonitor.exe
```

## Test

```bat
ruff check src tests scripts
pytest
python -m compileall src scripts
```

Tests do not call external APIs. They use local mappings and mocked responses.

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

## Notes

- Free-tier limits, fields, registration flows, and terms may change. Always refer to the official provider pages.
- Search results come from external providers and should be verified against original sources.
- This software does not constitute investment advice.

---

## 中文说明

当前版本：`v0.1.1`  
当前模式：`Public + Free API Network Mode`

Company Decision Monitor 是面向普通用户的公司研究与企业动态监控 Windows 桌面软件。v0.1.1 不要求用户导入 Excel、CSV 或本地公司数据库；用户可以通过公开数据源和自行申请的免费 API key 搜索全球主流国家和地区的公司、上市证券、法人实体、别名、基础 profile、新闻和市场信息。

本软件不提供投资建议，不提供交易、买入、卖出、下单、组合收益或目标价功能。

## 核心流程

1. 打开软件。
2. 进入「公司搜索」。
3. 输入公司名称、股票代码、简称、LEI 或注册号。
4. 未配置 key 的 provider 会自动跳过并显示状态。
5. 配置免费 API key 后，可提升搜索、详情和新闻覆盖。
6. 从真实搜索结果点击「添加自选」。
7. 在「自选公司」集中查看本机保存的公司。
8. 在「公司详情」查看 provider 返回的基础信息、来源和相关新闻。

## UI 使用说明

v0.1.1 UI Polish 将主流程收敛为「首页」「搜索公司」「自选公司」「公司详情」「设置」五个入口。

### 首页怎么用

- 在首页顶部输入公司名称、股票代码、简称或缩写，点击「搜索公司」进入联网搜索。
- 首页只展示关键状态：搜索能力、已配置免费 API key 数量、自选公司数量和缓存状态。
- 自选预览为空时，点击「去搜索公司」开始添加。
- 热门公司目前不显示无可靠来源的榜单，避免展示伪造数据。

### 搜索页怎么用

- 输入公司全称、股票代码、简称、缩写、LEI 或注册号后点击「搜索」。
- 结果会按「最佳匹配」「上市公司」「法人实体」「相关新闻」「可能相关」组织。
- 每条公司结果只显示核心字段；更多字段在「更多字段」折叠区查看。
- 局部 provider 错误和未配置项会收进「数据源诊断」，不会挤占主要搜索结果。

### 如何配置免费 API key

- 打开「设置」→「免费 API key」。
- 推荐优先配置：FMP、Alpha Vantage、Marketaux。
- 可选来源按折叠卡展示，展开后可查看注册入口、输入 key、保存或清除。
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

不同国家注册数据源的认证、字段、限流和服务条款差异较大。v0.1.1 只接入已完成基础映射的来源，其他来源保留为 registry/stub，以免展示不稳定或不可复现的数据。

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
| Financial Modeling Prep | 全球上市公司 | symbol search、profile、新闻 | 是：`FMP_API_KEY` | 免费层，以官方为准 | https://site.financialmodelingprep.com/developer/docs | 已实现基础搜索/新闻映射 | 免费层限制可能变化 |
| Alpha Vantage | 全球主流上市证券 | SYMBOL_SEARCH、OVERVIEW | 是：`ALPHA_VANTAGE_API_KEY` | 免费层，以官方为准 | https://www.alphavantage.co/support/#api-key | 已实现 SYMBOL_SEARCH 映射 | 免费频率限制较严格 |
| Marketaux | 全球财经新闻 | 新闻、媒体提及 | 是：`MARKETAUX_API_KEY` | 免费层，以官方为准 | https://www.marketaux.com/account/dashboard | 已实现新闻映射 | 不复制新闻全文 |
| OpenCorporates | 140+ jurisdictions 注册企业 | company search、jurisdiction、company number | 是：`OPENCORPORATES_API_TOKEN` | 以官方计划为准 | https://api.opencorporates.com/documentation/API-Reference | 已实现基础搜索映射 | 可能需要资格或付费计划 |
| UK Companies House | 英国公司注册信息 | company search、company number、status | 是：`COMPANIES_HOUSE_API_KEY` | 公共 API 免费但需认证 | https://developer.company-information.service.gov.uk/get-started | 已实现基础搜索映射 | 未配置时自动跳过 |
| Norway BRREG | 挪威企业注册 | organization number、legal name、address | 否 | 是 | https://data.brreg.no/enhetsregisteret/api/dokumentasjon/en/index.html | 已实现基础搜索映射 | 国家注册 fallback |
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

## API key 配置方式

1. 打开「设置」。
2. 在「免费 API key / token / GUID 配置」中填写对应 key。
3. 点击「保存 API key」。
4. 返回「公司搜索」执行查询。

Key 存储方式：

- 存储位置：`%APPDATA%\CompanyDecisionMonitor\api_keys.json`
- 只保存在用户本机。
- UI 显示 masked key。
- 日志和缓存 key 不包含明文 key。
- 安装包不包含用户 key、缓存、自选公司或 `.env`。

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

## 注意事项

- 免费层额度、字段覆盖、注册流程和服务条款可能变化，请以 provider 官方页面为准。
- 搜索结果来自外部 provider，用户需要核验原始来源。
- 本软件不构成投资建议。
