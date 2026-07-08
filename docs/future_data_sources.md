# Future Data Sources

以下 provider 已纳入 v0.1.1 registry 或 README 覆盖策略，但并不全部完成真实请求映射。

## 后续优先接入

- Finnhub
- Twelve Data
- Guardian Open Platform
- NewsAPI
- INSEE SIRENE
- Australia ABN Lookup
- Japan Corporate Number
- Singapore ACRA Open Data
- Corporations Canada

## 复杂地区策略

中国、印度、巴西、德国等地区暂不做 DOM 抓取，不绕过登录、验证码或反爬。优先使用 GLEIF、Wikidata、OpenCorporates 和用户配置的金融 provider fallback。
