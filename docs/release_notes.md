# Release Notes

## v0.1.0-ui-preview

版本定位：Windows 桌面端 UI 预览版。

当前版本用于展示 Company Decision Monitor 的桌面端信息架构、页面结构、空状态和交互占位，不包含真实业务数据。

## 已完成内容

- PyInstaller exe 构建。
- Inno Setup 安装包构建。
- 便携版 zip 构建。
- 首页 UI。
- 搜索页 UI。
- 自选页 UI。
- 公司详情页 UI。
- 热门公司 UI。
- 风险监控 UI。
- AI 总结 UI。
- 设置页 UI。
- 空状态设计。
- 旧样本产品数据清理。
- 工程结构整理。
- 统一 Windows 构建脚本。
- 便携版打包脚本。
- 构建清理脚本。

## 未实现内容

- 真实公司搜索。
- 自选公司持久化。
- 公司详情真实数据。
- 新闻、公告、财务、风险数据源。
- 风险规则引擎。
- AI 总结。
- 导出报告。

## 交付物

```text
dist\CompanyDecisionMonitor\CompanyDecisionMonitor.exe
dist\CompanyDecisionMonitor_Portable.zip
dist\installer\CompanyDecisionMonitor_Setup.exe
```

## 已知限制

- 当前仅用于 UI 和交互预览。
- 当前不包含真实公司数据。
- 当前不连接外部 API。
- 当前不执行联网搜索。
- 当前不保存真实用户自选列表。
- 当前不提供投资建议或交易功能。
