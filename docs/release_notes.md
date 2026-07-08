# Release Notes

## v0.1.1 - Public + Free API Network Mode

版本定位：Windows 桌面端公开数据源 + 免费 API key 联网版。

### 已完成

- 版本号更新为 `v0.1.1`。
- 模式更新为 `Public + Free API Network Mode`。
- 新增 API key 本机存储和 masking。
- 新增 provider registry 和 provider 状态模型。
- 新增 HTTP client 错误映射。
- 新增本地缓存，cache key 不包含明文 API key。
- 新增 fuzzy/query 工具。
- 实现基础 provider 映射：
  - FMP symbol search / news mapping。
  - Alpha Vantage SYMBOL_SEARCH mapping。
  - Marketaux news mapping。
  - GLEIF LEI mapping。
  - Wikidata entity mapping。
  - Nasdaq Symbol Directory parsing。
  - OpenCorporates mapping。
  - UK Companies House mapping。
  - Norway BRREG mapping。
- 设置页新增免费 API key / token / GUID 配置入口。
- 搜索页改为真实 provider 搜索入口。
- 公司详情页展示真实 provider 返回字段和相关新闻。
- 自选公司保存到用户本机。
- README 增加 API matrix、注册入口和国家覆盖策略。

### Stub / 未完成

- Guardian Open Platform。
- NewsAPI。
- INSEE SIRENE。
- ABN Lookup。
- Japan Corporate Number。
- Singapore ACRA Open Data。
- Corporations Canada。
- Finnhub / Twelve Data。
- 完整财务建模、风险规则引擎、AI 总结和报告导出。

### 交付物

- `dist\CompanyDecisionMonitor\CompanyDecisionMonitor.exe`
- `dist\CompanyDecisionMonitor_Portable.zip`
- `dist\installer\CompanyDecisionMonitor_Setup.exe`

### 安全说明

- 不硬编码真实 API key。
- 不把用户 key 打包进安装包。
- 不把 `.env` 打包进安装包。
- 未配置 key 的 provider 自动跳过。

## v0.1.0

版本定位：Windows 桌面端 UI 预览版。

已完成 PyInstaller exe、portable zip、Inno Setup 安装包、基础页面和空状态设计。
