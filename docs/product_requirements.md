# Product Requirements

Company Decision Monitor v0.1.3-bundled-open-source-runtime 是面向普通用户的公司研究与企业动态监控桌面软件。当前模式为 Open-Source Data Mode。

## 目标用户

- 公司研究人员。
- 投资研究人员。
- 企业动态跟踪用户。
- 希望默认不申请 API key、直接使用开源项目组合和公开无 key 数据源查询公司信息的普通用户。

## 核心场景

1. 搜索公司名称、股票代码、简称、LEI 或注册号。
2. 使用开源 / 无 key 数据源完成默认公司搜索。
3. 查看真实 provider 返回的公司基础信息和新闻。
4. 添加公司到本机自选。
5. 在设置页查看默认数据源状态、可选高级 API provider 和缓存。

## 当前边界

- 不做 CSV / Excel / 本地公司数据库导入。
- 不伪造公司、新闻、财务或风险数据。
- Advanced API Providers 默认关闭，普通用户无需配置 API key。
- AI 总结和风险规则引擎暂未接入。
