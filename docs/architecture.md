# Architecture

## 层次

- `src/cdm_desktop/ui/pages/`：页面级布局。
- `src/cdm_desktop/ui/components/`：复用 UI 组件。
- `src/cdm_desktop/public_api/`：v0.1.1 Public + Free API Network Mode 核心服务。
- `src/cdm_desktop/public_api/registry.py`：provider registry 和 API key 定义。
- `src/cdm_desktop/public_api/providers.py`：provider 请求和响应映射。
- `src/cdm_desktop/public_api/key_store.py`：本机 API key 存储和 masking。
- `src/cdm_desktop/public_api/cache.py`：本地缓存和安全 cache key。
- `src/cdm_desktop/public_api/search_service.py`：搜索聚合、去重、状态汇总。
- `src/cdm_desktop/public_api/watchlist_store.py`：本机自选公司持久化。

## 安全边界

- 用户 key 只保存到 AppData。
- 安装包不包含 `.env`、缓存、自选公司或用户 key。
- cache key 不包含明文 key/token/GUID。
- 未配置 key 的 provider 返回 `not_configured`，不会崩溃。

## 后续扩展

新增 provider 时先在 registry 登记，再实现 provider class 和映射测试，最后接入搜索聚合服务。
