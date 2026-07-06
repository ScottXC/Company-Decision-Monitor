# 架构说明

## 当前技术栈

- Python 3.12
- PySide6 桌面 GUI
- PyInstaller 打包

当前版本保留桌面端启动方式，不切换到 Web 前端或服务端架构。

## 目录职责

- `src/cdm_desktop/main.py`：应用入口。
- `src/cdm_desktop/app.py`：QApplication 初始化和全局样式加载。
- `src/cdm_desktop/ui/main_window.py`：AppShell、侧栏、顶栏和页面路由。
- `src/cdm_desktop/ui/pages/`：页面级布局。
- `src/cdm_desktop/ui/components/`：可复用 UI 组件。
- `src/cdm_desktop/services/preview_*.py`：未来数据接口占位，当前不调用网络、不写数据库。
- `src/cdm_desktop/types/`：页面和未来服务共享类型。
- `src/cdm_desktop/store/`：轻量 UI 状态。
- `docs/`：产品、UI、架构和数据源规划。

## 页面层规则

页面只负责组合组件和响应占位交互，不直接写业务数据处理逻辑。

## 组件层规则

组件只负责展示、布局和通用交互。空状态、指标卡、占位表格等复用组件集中在 `ui/components`。

## 服务层规则

当前服务层只提供未来扩展接口，并返回空数组、`None` 或 UI 状态说明。不接入真实 API、爬虫、数据库写入或 LLM。

## 后续扩展方式

1. 先在服务层实现真实数据接口。
2. 再在 store 中加入持久化状态。
3. 最后让页面消费真实服务结果。
4. 每个真实功能接入前必须保留空状态和错误状态。
