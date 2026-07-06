# Company Decision Monitor

当前版本：**v0.1.0-ui-preview**

当前状态：**UI Preview Mode**

Company Decision Monitor 是一个面向公司研究、投资研究、企业动态跟踪的 Windows 桌面端信息监控工具雏形。当前版本只提供正式软件 UI、页面结构和交互占位，不包含真实公司数据，不接入真实 API，不执行真实联网搜索，不运行真实爬虫，不写入真实业务数据。

## 当前交付物

构建完成后应生成：

```text
dist\CompanyDecisionMonitor\CompanyDecisionMonitor.exe
dist\CompanyDecisionMonitor_Portable.zip
dist\installer\CompanyDecisionMonitor_Setup.exe
```

## 直接运行 exe

```bat
dist\CompanyDecisionMonitor\CompanyDecisionMonitor.exe
```

## 开发启动

```bat
run_dev.bat
```

或者：

```bat
python -m cdm_desktop.main
```

## 重新构建全部交付物

```bat
build.bat
```

该命令会执行：

1. 清理旧构建；
2. `ruff check src tests scripts`；
3. `pytest`；
4. PyInstaller onedir 构建；
5. 生成便携版 zip；
6. 查找并调用 Inno Setup；
7. 校验 exe、zip、setup 安装包；
8. 输出交付物清单和文件大小。

也可以直接运行：

```bat
python scripts\build_windows.py
```

## 生成便携版 zip

如果 PyInstaller 产物已经存在，可单独生成便携版：

```bat
python scripts\package_portable.py
```

输出：

```text
dist\CompanyDecisionMonitor_Portable.zip
```

zip 内部根目录为：

```text
CompanyDecisionMonitor\
```

## 生成安装包

安装包脚本：

```text
installer\CompanyDecisionMonitor.iss
```

手动生成：

```bat
ISCC.exe installer\CompanyDecisionMonitor.iss
```

输出：

```text
dist\installer\CompanyDecisionMonitor_Setup.exe
```

## 确认 Inno Setup 可用

```bat
where ISCC.exe
```

本项目构建脚本会按以下顺序查找 Inno Setup 编译器：

1. PATH 中的 `ISCC.exe`
2. PATH 中的 `iscc.exe`
3. 环境变量 `INNO_SETUP_COMPILER`
4. `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`
5. `C:\Program Files\Inno Setup 6\ISCC.exe`

如果找不到，构建会失败并输出实际检查过的路径。

## 清理旧构建

普通清理，不删除最新 dist：

```bat
python scripts\clean_build.py
```

完整清理，包括 `dist/`、旧安装包和旧 zip：

```bat
python scripts\clean_build.py --full
```

## 已完成 UI 模块

- 首页 Dashboard
- 公司搜索 Search
- 公司详情 Company Detail
- 自选公司 Watchlist
- 热门公司 Hot Companies
- 风险监控 Risk Monitor
- AI 总结 AI Summary
- 设置 Settings
- 统一 AppShell、侧栏、顶栏、全局搜索栏
- 空状态、指标卡、占位表格、占位图表、状态徽章

## 当前未实现

- 真实公司搜索
- 自选公司持久化
- 公司详情真实数据
- 新闻、公告、财务、风险数据源
- 风险规则引擎
- AI 总结
- 导出报告

## 常见问题

### exe 能生成但安装包不能生成怎么办？

先确认 Inno Setup 编译器可用：

```bat
where ISCC.exe
```

如果找不到，请安装 Inno Setup，或设置环境变量 `INNO_SETUP_COMPILER` 指向 `ISCC.exe`。

### `where ISCC.exe` 找不到怎么办？

检查 Inno Setup 是否安装，并确认安装目录已经加入 PATH。也可以设置：

```bat
set INNO_SETUP_COMPILER=D:\Software\Inno Setup 7\ISCC.exe
```

### 搜索为什么没有真实结果？

当前版本是 UI Preview Mode，搜索页只展示搜索体验和空状态，不接入真实公司搜索数据源。

### 为什么自选公司不保存？

当前版本不写入真实业务数据库，自选公司页面只展示未来列表结构和空状态。

### 如何重新构建？

```bat
build.bat
```

### 如何清理缓存？

```bat
python scripts\clean_build.py
```

如需完整清理：

```bat
python scripts\clean_build.py --full
```

## 注意事项

- 当前不包含真实公司数据。
- 当前不接入真实 API。
- 当前不执行真实联网搜索。
- 当前不运行真实爬虫。
- 当前不新增真实数据库依赖。
- 当前不提供投资建议、交易建议、买入、卖出、下单、组合收益或 P&L 功能。
