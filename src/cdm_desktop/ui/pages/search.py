from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api import PublicSearchService, SearchResponse
from cdm_desktop.public_api.models import CompanyResult, NewsItem, ProviderStatus
from cdm_desktop.public_api.search_service import REGION_OPTIONS, region_label
from cdm_desktop.public_api.watchlist_store import WatchlistStore
from cdm_desktop.public_api.xueqiu_external_link import build_xueqiu_external_link
from cdm_desktop.ui.components import (
    CollapsibleSection,
    DetailGrid,
    EmptyState,
    LoadingState,
    PageHeader,
    SectionCard,
    StatusBadge,
    friendly_state_label,
    friendly_state_tone,
    provider_status_summary,
    sanitize_error_message,
    scroll_container,
)
from cdm_desktop.ui.widgets import FunctionWorker

SCOPES = [
    ("全部", "all"),
    ("上市公司", "financial"),
    ("法人实体", "entity"),
    ("新闻", "news"),
    ("可能相关", "related"),
]


class SearchPage(QWidget):
    route = "/search"
    page_title = "搜索公司"

    def __init__(
        self,
        navigate: Callable[[str], None],
        paths: AppPaths | None = None,
        *,
        on_company_selected: Callable[[CompanyResult], None] | None = None,
        on_watchlist_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.navigate = navigate
        self.paths = paths
        self.on_company_selected = on_company_selected
        self.on_watchlist_changed = on_watchlist_changed
        self.current_scope = "all"
        self.current_region = "all"
        self.service = PublicSearchService(paths)
        self.watchlist = WatchlistStore(paths)
        self.thread_pool = QThreadPool.globalInstance()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, self.layout = scroll_container()
        root.addWidget(scroll)

        self.layout.addWidget(
            PageHeader(
                "搜索公司",
                "先选择地区缩小数据源范围，再输入公司名称、股票代码、简称、缩写、LEI 或注册号。",
                secondary_text="配置免费 API key",
                secondary_action=lambda: self.navigate("/settings"),
            )
        )
        self.layout.addWidget(self._search_panel())

        result_area = QWidget()
        result_grid = QGridLayout(result_area)
        result_grid.setContentsMargins(0, 0, 0, 0)
        result_grid.setHorizontalSpacing(14)
        result_grid.setVerticalSpacing(14)
        self.result_host = QVBoxLayout()
        self.result_host.setSpacing(12)
        self.side_host = QVBoxLayout()
        self.side_host.setSpacing(12)
        result_grid.addLayout(self.result_host, 0, 0)
        result_grid.addLayout(self.side_host, 0, 1)
        result_grid.setColumnStretch(0, 3)
        result_grid.setColumnStretch(1, 1)
        self.layout.addWidget(result_area)
        self._show_initial_state()
        self.layout.addStretch()

    def set_query(self, keyword: str) -> None:
        self.input.setText(keyword)
        self.input.setFocus()

    def run_search(self) -> None:
        keyword = self.input.text().strip()
        self._clear_results()
        if not keyword:
            self._show_initial_state()
            return
        selected_count = self.service.selected_provider_count(
            region_filter=self.current_region,
            scope_filter=self.current_scope,
        )
        self.result_host.addWidget(
            LoadingState(
                f"正在按“{region_label(self.current_region)}”调用 {selected_count} 个匹配数据源。"
                "未配置的增强来源会自动跳过。"
            )
        )
        self.side_host.addWidget(
            SectionCard(
                "搜索状态",
                "正在请求公开数据源和已配置的免费 API provider。局部失败会收进诊断，不会阻塞其他来源。",
            )
        )
        worker = FunctionWorker(
            self.service.search,
            keyword,
            20,
            region_filter=self.current_region,
            scope_filter=self.current_scope,
        )
        worker.signals.finished.connect(self._render_response)
        worker.signals.error.connect(self._render_error)
        self.thread_pool.start(worker)

    def _search_panel(self) -> SectionCard:
        card = SectionCard("联网搜索", "结果来自公开数据源和已配置的免费 API provider；不会展示伪造公司数据。")

        region_row = QHBoxLayout()
        region_label_widget = QLabel("地区 / 国家")
        region_label_widget.setObjectName("MutedText")
        self.region_filter = QComboBox()
        self.region_filter.setMinimumWidth(260)
        for value, label, description in REGION_OPTIONS:
            self.region_filter.addItem(label, value)
            self.region_filter.setItemData(self.region_filter.count() - 1, description, Qt.ItemDataRole.ToolTipRole)
        self.region_filter.currentIndexChanged.connect(self._region_changed)
        self.region_hint = QLabel(str(self.region_filter.itemData(0, Qt.ItemDataRole.ToolTipRole) or ""))
        self.region_hint.setObjectName("MutedText")
        self.region_hint.setWordWrap(True)
        region_row.addWidget(region_label_widget)
        region_row.addWidget(self.region_filter)
        region_row.addWidget(self.region_hint, 1)
        card.layout.addLayout(region_row)

        search_row = QHBoxLayout()
        keyword_label = QLabel("关键词")
        keyword_label.setObjectName("MutedText")
        self.input = QLineEdit()
        self.input.setObjectName("HeroSearchInput")
        self.input.setPlaceholderText("搜索公司、股票代码、简称或缩写，例如 Apple、AAPL、腾讯、IBM")
        self.input.returnPressed.connect(self.run_search)
        search_btn = QPushButton("搜索")
        search_btn.setObjectName("PrimaryButton")
        search_btn.clicked.connect(self.run_search)
        search_row.addWidget(keyword_label)
        search_row.addWidget(self.input, 1)
        search_row.addWidget(search_btn)
        card.layout.addLayout(search_row)

        hint = QLabel("支持公司全称、股票代码、简称、缩写、LEI、注册号。匹配不确定时会归入“可能相关”。")
        hint.setObjectName("MutedText")
        hint.setWordWrap(True)
        card.layout.addWidget(hint)

        scope_row = QHBoxLayout()
        scope_label = QLabel("结果类型")
        scope_label.setObjectName("MutedText")
        scope_row.addWidget(scope_label)
        self.scope_group = QButtonGroup(self)
        self.scope_group.setExclusive(True)
        for label, value in SCOPES:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setObjectName("ScopeChip")
            button.setProperty("scope", value)
            if value == "all":
                button.setChecked(True)
            button.clicked.connect(self._scope_changed)
            self.scope_group.addButton(button)
            scope_row.addWidget(button)
        scope_row.addStretch()
        card.layout.addLayout(scope_row)
        return card

    def _scope_changed(self) -> None:
        button = self.sender()
        if isinstance(button, QPushButton):
            self.current_scope = str(button.property("scope"))

    def _region_changed(self) -> None:
        self.current_region = str(self.region_filter.currentData() or "all")
        self.region_hint.setText(
            str(self.region_filter.itemData(self.region_filter.currentIndex(), Qt.ItemDataRole.ToolTipRole) or "")
        )

    def _render_response(self, result: object) -> None:
        self._clear_results()
        if not isinstance(result, SearchResponse):
            self._render_error("搜索服务返回了未知结果。")
            return
        self._render_light_status(result.statuses, result.from_cache)
        companies = self._filter_companies(result.companies)
        groups = self._group_companies(companies)
        if not companies and not (result.news and self.current_scope in {"all", "news"}):
            self.result_host.addWidget(self._empty_result_card())
        else:
            for title, rows in groups:
                if rows:
                    self.result_host.addWidget(self._company_group(title, rows))
            if result.news and self.current_scope in {"all", "news"}:
                self.result_host.addWidget(self._news_group(result.news[:8]))
        self.side_host.addWidget(self._diagnostics(result.statuses))
        self.side_host.addStretch()

    def _render_light_status(self, statuses: list[ProviderStatus], from_cache: bool) -> None:
        summary = provider_status_summary(statuses)
        missing = sum(1 for item in statuses if item.state == "not_configured")
        failed = sum(1 for item in statuses if item.state in {"failed", "invalid_key", "rate_limited"})
        card = SectionCard("覆盖状态")
        row = QGridLayout()
        status_items = [("上市公司", "financial"), ("法人实体", "registry"), ("公开补充", "global"), ("新闻", "news")]
        for index, (label, category) in enumerate(status_items):
            state = summary.get(category, "部分可用")
            tone = "success" if state == "正常" else "warning" if state in {"部分可用", "未配置"} else "danger"
            row.addWidget(StatusBadge(f"{label}：{state}", tone), index // 2, index % 2)
        card.layout.addLayout(row)
        if missing:
            card.layout.addWidget(StatusBadge("部分增强数据源未配置免费 API key，覆盖可能受限。", "warning"))
        if failed:
            card.layout.addWidget(StatusBadge("部分数据源暂时不可用，已继续尝试其他来源。", "warning"))
        if from_cache:
            card.layout.addWidget(StatusBadge("当前展示了本地缓存结果。", "info"))
        self.side_host.addWidget(card)

    def _company_group(self, title: str, companies: list[CompanyResult]) -> SectionCard:
        card = SectionCard(f"{title} · {len(companies)}")
        for company in companies:
            card.layout.addWidget(self._company_card(company))
        return card

    def _company_card(self, company: CompanyResult) -> SectionCard:
        identity = company.symbol or company.lei or company.company_number or company.registry_number or "暂无标识"
        region = company.exchange or company.market or company.jurisdiction or company.country or "暂无地区"
        card = SectionCard()
        card.setObjectName("SearchResultCard")
        top = QHBoxLayout()
        title_box = QVBoxLayout()
        name = QLabel(company.name or identity)
        name.setObjectName("SectionTitle")
        meta = QLabel(f"{identity} · {region}")
        meta.setObjectName("MutedText")
        meta.setWordWrap(True)
        title_box.addWidget(name)
        title_box.addWidget(meta)
        top.addLayout(title_box, 1)
        top.addWidget(StatusBadge(company.provider, "info"))
        if company.match_score:
            tone = "success" if company.match_score >= 85 else "warning"
            top.addWidget(StatusBadge(f"匹配 {company.match_score}", tone))
        card.layout.addLayout(top)
        reason = QLabel(company.match_reason or "公开来源返回")
        reason.setObjectName("MutedText")
        reason.setWordWrap(True)
        card.layout.addWidget(reason)
        row = QHBoxLayout()
        detail_btn = QPushButton("查看详情")
        detail_btn.clicked.connect(lambda _checked=False, c=company: self._open_detail(c))
        add_btn = QPushButton("添加自选")
        add_btn.setObjectName("PrimaryButton")
        add_btn.clicked.connect(lambda _checked=False, c=company: self._add_watchlist(c))
        row.addWidget(detail_btn)
        row.addWidget(add_btn)
        if company.source_url:
            source_btn = QPushButton("打开来源")
            source_btn.clicked.connect(lambda _checked=False, url=company.source_url: QDesktopServices.openUrl(QUrl(url)))
            row.addWidget(source_btn)
        row.addStretch()
        card.layout.addLayout(row)

        advanced = CollapsibleSection("更多字段", expanded=False)
        advanced.body_layout.addWidget(
            DetailGrid(
                [
                    ("Legal name", company.legal_name),
                    ("LEI", company.lei),
                    ("注册号", company.company_number or company.registry_number),
                    ("交易所 / 市场", company.exchange or company.market),
                    ("官网", company.website),
                    ("更新时间", company.updated_at),
                ],
                columns=2,
            )
        )
        xueqiu_link = build_xueqiu_external_link(
            symbol=company.symbol,
            exchange=company.exchange,
            market=company.market,
            company_name=company.name or company.display_name or company.legal_name,
        )
        if xueqiu_link.is_direct_stock_link:
            external_row = QHBoxLayout()
            external_row.addWidget(StatusBadge("外部链接", "info"))
            external_row.addWidget(StatusBadge("不抓取内容", "warning"))
            open_xueqiu = QPushButton("打开雪球")
            open_xueqiu.clicked.connect(lambda _checked=False, url=xueqiu_link.url: QDesktopServices.openUrl(QUrl(url)))
            external_row.addWidget(open_xueqiu)
            external_row.addStretch()
            advanced.body_layout.addLayout(external_row)
        card.layout.addWidget(advanced)
        return card

    def _news_group(self, news_items: list[NewsItem]) -> SectionCard:
        card = SectionCard("相关新闻", "只展示标题、来源、时间和链接，不复制新闻全文。")
        for item in news_items:
            row = SectionCard(item.title or "未命名新闻", f"{item.provider} · {item.source or '未知来源'} · {item.published_at or '暂无时间'}")
            if item.snippet:
                snippet = QLabel(item.snippet[:220])
                snippet.setWordWrap(True)
                snippet.setObjectName("MutedText")
                row.layout.addWidget(snippet)
            if item.url:
                btn = QPushButton("打开链接")
                btn.clicked.connect(lambda _checked=False, url=item.url: QDesktopServices.openUrl(QUrl(url)))
                row.layout.addWidget(btn)
            card.layout.addWidget(row)
        return card

    def _diagnostics(self, statuses: list[ProviderStatus]) -> CollapsibleSection:
        diagnostics = CollapsibleSection("数据源诊断", "局部错误和未配置项默认折叠，避免干扰搜索结果。", expanded=False)
        for status in statuses:
            row = QHBoxLayout()
            row.addWidget(StatusBadge(status.display_name, "neutral"))
            row.addWidget(StatusBadge(friendly_state_label(status.state), friendly_state_tone(status.state)))
            message = QLabel(sanitize_error_message(status.message))
            message.setWordWrap(True)
            message.setObjectName("MutedText")
            row.addWidget(message, 1)
            diagnostics.body_layout.addLayout(row)
        return diagnostics

    def _group_companies(self, companies: list[CompanyResult]) -> list[tuple[str, list[CompanyResult]]]:
        best = [item for item in companies if item.match_score >= 85][:5]
        financial = [
            item
            for item in companies
            if item.category == "financial" or item.provider_id in {"fmp", "alpha_vantage", "nasdaq_directory"}
        ]
        entity = [
            item
            for item in companies
            if item.category in {"global", "registry"}
            or item.provider_id in {"gleif", "opencorporates", "companies_house", "norway_brreg"}
        ]
        related = [item for item in companies if item.match_score < 85]
        return [
            ("最佳匹配", best),
            ("上市公司", financial),
            ("法人实体", entity),
            ("可能相关", related),
        ]

    def _filter_companies(self, companies: list[CompanyResult]) -> list[CompanyResult]:
        if self.current_scope == "all":
            return companies
        if self.current_scope == "news":
            return []
        if self.current_scope == "financial":
            return [
                item
                for item in companies
                if item.category == "financial" or item.provider_id in {"fmp", "alpha_vantage", "nasdaq_directory"}
            ]
        if self.current_scope == "entity":
            return [
                item
                for item in companies
                if item.category in {"global", "registry"}
                or item.provider_id in {"gleif", "opencorporates", "companies_house", "norway_brreg"}
            ]
        if self.current_scope == "related":
            return [item for item in companies if item.match_score < 85]
        return companies

    def _empty_result_card(self) -> EmptyState:
        return EmptyState(
            "未找到高置信度匹配",
            "请尝试使用公司全称、股票代码、英文名、注册号或 LEI；也可以在设置页配置免费 API key 提升覆盖范围。",
            action_text="配置免费 API key",
            action=lambda: self.navigate("/settings"),
        )

    def _add_watchlist(self, company: CompanyResult) -> None:
        self.watchlist.add(company)
        if self.on_watchlist_changed:
            self.on_watchlist_changed()
        QMessageBox.information(self, "自选公司", "已添加到本机自选公司。")

    def _open_detail(self, company: CompanyResult) -> None:
        if self.on_company_selected:
            self.on_company_selected(company)
        else:
            self.navigate("/company/placeholder")

    def _render_error(self, message: str) -> None:
        self._clear_results()
        self.result_host.addWidget(
            EmptyState(
                "搜索失败",
                sanitize_error_message(message),
                action_text="重试",
                action=self.run_search,
            )
        )
        self.side_host.addWidget(
            SectionCard("数据源诊断", "所有可用来源都未能返回结果。请检查网络、免费 API key 或稍后重试。")
        )

    def _show_initial_state(self) -> None:
        self.result_host.addWidget(
            EmptyState(
                "开始搜索公司",
                "输入公司名、股票代码、简称、缩写、LEI 或注册号后开始查询。未配置的增强数据源会自动跳过。",
                action_text="配置免费 API key",
                action=lambda: self.navigate("/settings"),
            )
        )
        self.side_host.addWidget(
            SectionCard(
                "结果预览",
                "搜索后左侧显示公司和新闻列表，右侧显示数据源覆盖、缓存和诊断状态。",
            )
        )
        self.side_host.addStretch()

    def _clear_results(self) -> None:
        self._clear_layout(self.result_host)
        self._clear_layout(self.side_host)

    def _clear_layout(self, layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget:
                widget.deleteLater()
            elif child_layout:
                self._clear_layout(child_layout)
