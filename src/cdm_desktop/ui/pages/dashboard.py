from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop import APP_MODE_LABEL
from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api import PublicSearchService
from cdm_desktop.public_api.cache import ApiCache
from cdm_desktop.public_api.key_store import ApiKeyStore
from cdm_desktop.public_api.registry import ProviderRegistry
from cdm_desktop.public_api.watchlist_store import WatchlistStore
from cdm_desktop.ui.components import (
    EmptyState,
    MetricCard,
    SectionCard,
    StatusBadge,
    metric_grid,
    provider_status_summary,
    scroll_container,
)
from cdm_desktop.ui.widgets import FunctionWorker


class DashboardPage(QWidget):
    route = "/dashboard"
    page_title = "工作台"

    def __init__(self, navigate: Callable[[str], None], paths: AppPaths | None = None) -> None:
        super().__init__()
        self.navigate = navigate
        self.paths = paths
        self.search_service = PublicSearchService(paths)
        self.watchlist = WatchlistStore(paths)
        self.key_store = ApiKeyStore(paths)
        self.registry = ProviderRegistry()
        self.cache = ApiCache(paths)
        self.thread_pool = QThreadPool.globalInstance()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, self.layout = scroll_container()
        root.addWidget(scroll)
        self.refresh()

    def refresh(self) -> None:
        self._clear()
        items = self.watchlist.list_items()
        statuses = self.search_service.provider_statuses()
        summary = provider_status_summary(statuses)
        configured_keys = sum(1 for item in self.registry.key_definitions() if self.key_store.status(item.key_name)[0])

        self.layout.addWidget(self._command_center())
        self.layout.addWidget(
            metric_grid(
                [
                    MetricCard("搜索能力", self._search_capacity_label(statuses), APP_MODE_LABEL),
                    MetricCard("免费 API key", f"{configured_keys} / {len(self.registry.key_definitions())}", "未配置的增强来源会自动跳过"),
                    MetricCard("自选公司", f"{len(items)} 家", "仅保存在用户本机"),
                    MetricCard("缓存状态", self._cache_label(), "可在设置页清理"),
                ],
                columns=4,
            )
        )

        workspace = QWidget()
        grid = QGridLayout(workspace)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        grid.addWidget(self._watchlist_preview(items), 0, 0)
        grid.addWidget(self._source_summary(summary), 0, 1)
        grid.addWidget(self._market_intel_panel(), 1, 0, 1, 2)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 1)
        self.layout.addWidget(workspace)
        self.layout.addStretch()

    def _command_center(self) -> SectionCard:
        card = SectionCard("研究工作台", "搜索公司、查看本机自选、检查公开数据源状态。")
        card.setObjectName("CommandPanel")
        title = QLabel("Company Decision Monitor")
        title.setObjectName("HeroTitle")
        subtitle = QLabel("公司研究与企业动态监控桌面工具 · Public + Free API Network Mode")
        subtitle.setObjectName("HeroSubtitle")
        subtitle.setWordWrap(True)
        card.layout.addWidget(title)
        card.layout.addWidget(subtitle)

        row = QHBoxLayout()
        self.quick_input = QLineEdit()
        self.quick_input.setObjectName("HeroSearchInput")
        self.quick_input.setPlaceholderText("搜索公司、股票代码、简称或缩写，例如 Apple、AAPL、腾讯、IBM")
        self.quick_input.returnPressed.connect(self._quick_search)
        search_btn = QPushButton("搜索公司")
        search_btn.setObjectName("PrimaryButton")
        search_btn.clicked.connect(self._quick_search)
        settings_btn = QPushButton("配置免费 API key")
        settings_btn.clicked.connect(lambda: self.navigate("/settings"))
        row.addWidget(self.quick_input, 1)
        row.addWidget(search_btn)
        row.addWidget(settings_btn)
        card.layout.addLayout(row)

        nav = QHBoxLayout()
        for text, route in [("搜索公司", "/search"), ("自选清单", "/watchlist"), ("数据源设置", "/settings")]:
            button = QPushButton(text)
            button.clicked.connect(lambda _checked=False, target=route: self.navigate(target))
            nav.addWidget(button)
        nav.addStretch()
        card.layout.addLayout(nav)
        return card

    def _watchlist_preview(self, items: list) -> SectionCard:
        card = SectionCard("自选清单", "本机保存的关注公司，最多显示 5 家。")
        if not items:
            card.layout.addWidget(
                EmptyState(
                    "暂无自选公司",
                    "搜索公司后，点击“添加自选”即可在这里集中跟踪。",
                    action_text="去搜索公司",
                    action=lambda: self.navigate("/search"),
                )
            )
            return card
        for item in items[:5]:
            row = QHBoxLayout()
            row.addWidget(QLabel(item.name or item.symbol or "未命名公司"), 1)
            row.addWidget(StatusBadge(item.symbol or item.lei or item.company_number or "暂无标识", "neutral"))
            open_btn = QPushButton("详情")
            open_btn.clicked.connect(lambda _checked=False, company=item: self._open_company(company))
            row.addWidget(open_btn)
            card.layout.addLayout(row)
        if len(items) > 5:
            card.layout.addWidget(StatusBadge(f"还有 {len(items) - 5} 家在自选页查看", "info"))
        return card

    def _source_summary(self, summary: dict[str, str]) -> SectionCard:
        card = SectionCard("数据源状态", "首页只显示大类状态，详细 provider 诊断在设置页。")
        rows = [
            ("核心搜索源", summary.get("financial", "部分可用")),
            ("公司信息源", summary.get("registry", "部分可用")),
            ("新闻源", summary.get("news", "未配置")),
            ("公开补充源", summary.get("global", "正常")),
        ]
        for label, state in rows:
            row = QHBoxLayout()
            row.addWidget(QLabel(label), 1)
            tone = "success" if state == "正常" else "warning" if state in {"未配置", "部分可用"} else "danger"
            row.addWidget(StatusBadge(state, tone))
            card.layout.addLayout(row)
        test_btn = QPushButton("测试数据源连接")
        test_btn.clicked.connect(self._test_sources)
        card.layout.addWidget(test_btn)
        return card

    def _market_intel_panel(self) -> SectionCard:
        card = SectionCard("市场情报", "当前不显示无可靠来源的热门榜单或投资建议。")
        card.layout.addWidget(
            EmptyState(
                "热门公司暂未接入可靠来源",
                "后续只会基于真实新闻、搜索和公开来源热度展示，不会生成伪造公司。",
            )
        )
        return card

    def _quick_search(self) -> None:
        keyword = self.quick_input.text().strip()
        self.navigate("/search")
        parent = self.window()
        search_page = getattr(parent, "search_page", None)
        if search_page and hasattr(search_page, "set_query"):
            search_page.set_query(keyword)
            if keyword:
                search_page.run_search()

    def _test_sources(self) -> None:
        worker = FunctionWorker(self.search_service.search, "Apple", 5, False)
        worker.signals.finished.connect(lambda _result: self.refresh())
        worker.signals.error.connect(lambda _error: self.refresh())
        self.thread_pool.start(worker)

    def _open_company(self, company: object) -> None:
        parent = self.window()
        opener = getattr(parent, "_open_company_detail", None)
        if callable(opener):
            opener(company)

    def _search_capacity_label(self, statuses: list) -> str:
        usable = sum(1 for item in statuses if item.state in {"enabled", "empty"})
        failed = sum(1 for item in statuses if item.state in {"failed", "invalid_key", "rate_limited"})
        if usable and failed:
            return "部分启用"
        if usable:
            return "已启用"
        return "需要配置"

    def _cache_label(self) -> str:
        size = self.cache.size_bytes()
        if size <= 0:
            return "正常"
        if size < 10 * 1024 * 1024:
            return "正常"
        return "可清理"

    def _clear(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
