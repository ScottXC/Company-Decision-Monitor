# Public + Free API Network Mode

v0.1.1 将软件从纯 UI 预览升级为公开数据源 + 用户配置免费 API key 的联网模式。

## 设计原则

- 普通用户不需要导入本地 Excel、CSV 或公司数据库。
- 用户可以选择自行申请免费 API key。
- 未配置 key 的 provider 不报错、不阻断主流程。
- 所有外部数据必须显示 provider 和来源。
- 不伪造公司、新闻、财务或风险数据。
- 不绕过登录、验证码、反爬或访问限制。

## Provider 分层

1. 全球法人实体：GLEIF、OpenCorporates。
2. 国家注册企业：Companies House、INSEE、ABN、Japan NTA、ACRA、BRREG、Canada。
3. 上市证券：FMP、Alpha Vantage、Nasdaq Symbol Directory。
4. 新闻：Marketaux、Guardian、NewsAPI、RSS。

## Key 存储

Key 存储在用户 AppData 的 `api_keys.json`。UI 显示 masked key；缓存 key 不包含明文 key；安装包不包含任何用户配置。

## 当前限制

免费 API provider 的额度、字段、注册流程会变化。部分 provider 在 v0.1.1 仅作为 registry/stub 展示，后续版本再接入完整请求映射。
## v0.1.1 UI Polish

v0.1.1 UI Polish 不改变 provider、API key、缓存和自选数据的核心逻辑，只整理信息层级：

- 主导航收敛为首页、搜索公司、自选公司、公司详情、设置。
- 首页只展示搜索入口、关键状态、自选预览和数据源大类摘要。
- 搜索页按最佳匹配、上市公司、法人实体、相关新闻和可能相关分组。
- provider 局部错误、未配置项和技术诊断默认折叠，不占用主内容。
- 设置页按数据源总览、免费 API key、公开数据源、搜索设置、缓存与隐私、关于软件分组。
- UI 不展示 traceback、原始异常对象或明文 API key。

详细结构见 `docs/ui_structure.md`。
