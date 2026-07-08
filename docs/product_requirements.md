# Product Requirements

Company Decision Monitor v0.1.1 是面向普通用户的公司研究与企业动态监控桌面软件。当前模式为 Public + Free API Network Mode。

## 目标用户

- 公司研究人员。
- 投资研究人员。
- 企业动态跟踪用户。
- 希望用公开数据源和免费 API key 查询公司信息的普通用户。

## 核心场景

1. 搜索公司名称、股票代码、简称、LEI 或注册号。
2. 配置免费 API key 提升搜索覆盖。
3. 查看真实 provider 返回的公司基础信息和新闻。
4. 添加公司到本机自选。
5. 在设置页查看 provider 状态、注册入口和缓存。

## 当前边界

- 不做 CSV / Excel / 本地公司数据库导入。
- 不伪造公司、新闻、财务或风险数据。
- 未配置 key 的 provider 自动跳过。
- AI 总结和风险规则引擎暂未接入。
