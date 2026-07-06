# Changelog

## 0.1.0 - 2026-06-26

- Initial Windows desktop MVP scaffold.
- Added local SQLite schema, PySide6 shell, ingestion, parsing, event detection, alerts, exports, scheduler, tests, and packaging scripts.
- Added self-selected company search/list workflow, hot company recommendations, event/alert delete actions, and a local recycle bin with restore/permanent delete.
- Improved card scaling and compact self-selected company rows for denser desktop usage.
- Replaced popup company search with a right-side drawer search panel.
- Added explicit online company lookup from the drawer search panel.
- Removed built-in demo company/document/source content from product code and documentation.
- Hardened event, alert, watchlist, and source delete actions with real recycle-bin persistence and user-facing failure messages.
- Replaced local company discovery with a dedicated API-key-free `联网搜索` module.
- Added SEC, Nasdaq Trader, HKEX securities, Stock Connect, RSS, and user-configured IR search provider architecture.
- Added online search cache/settings tables and provider controls under `设置 → 联网搜索`.
- Removed the old generic quote-search client and local company discovery service from product code.
