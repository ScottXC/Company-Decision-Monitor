# UI Reference

v0.1.1 UI 使用金融终端式布局：左侧导航、顶部全局搜索、卡片式信息区和 provider 状态提示。

## 状态规范

- `Public + Free API Network Mode`：当前模式。
- `未配置`：provider 需要免费 API key，但用户尚未配置。
- `已启用`：provider 无需 key 或已配置 key。
- `Stub`：已列入 registry，但当前版本未完成真实请求。
- `失败 / 频率限制 / key 无效`：网络层或 provider 返回错误。

## 数据显示原则

- 不显示伪造公司。
- 不显示伪造新闻。
- 不显示伪造财务数据。
- 缺失字段显示“暂无数据”。
