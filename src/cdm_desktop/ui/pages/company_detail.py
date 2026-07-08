from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api import PublicSearchService, SearchResponse
from cdm_desktop.public_api.models import CompanyResult, ProviderStatus
from cdm_desktop.public_api.watchlist_store import WatchlistStore
from cdm_desktop.ui.components import (
    DetailGrid,
    EmptyState,
    LoadingState,
    MetricCard,
    PageHeader,
    SectionCard,
    StatusBadge,
    friendly_state_label,
    friendly_state_tone,
    metric_grid,
    sanitize_error_message,
    scroll_container,
)
from cdm_desktop.ui.widgets import FunctionWorker


class CompanyDetailPage(QWidget):
    route = "/company/placeholder"
    page_title = "公司档案"

    def __init__(self, navigate: Callable[[str], None], paths: AppPaths | None = None) -> None:
        super().__init__()
        self.navigate = navigate
        self.paths = paths
        self.current_company: CompanyResult | None = None
        self.service = PublicSearchService(paths)
        self.watchlist = WatchlistStore(paths)
        self.thread_pool = QThreadPool.globalInstance()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, self.layout = scroll_container()
        root.addWidget(scroll)
        self.refresh()

    def set_company(self, company: CompanyResult) -> None:
        self.current_company = company

    def refresh(self) -> None:
        self._clear()
        company = self.current_company
        if not company:
            self.layout.addWidget(
                PageHeader(
                    "公司档案",
                    "从搜索结果或自选公司打开后，这里会展示公开数据源返回的公司资料、新闻和来源状态。",
                    primary_text="搜索公司",
                    primary_action=lambda: self.navigate("/search"),
                )
            )
            self.layout.addWidget(EmptyState("尚未选择公司", "请先在搜索页选择一个真实公开数据源返回的公司结果。"))
            self.layout.addStretch()
            return

        self.layout.addWidget(self._company_header(company))
        self.layout.addWidget(self._summary_cards(company))
        self.layout.addWidget(self._tabs(company))
        self._load_related()
        self.layout.addStretch()

    def _company_header(self, company: CompanyResult) -> SectionCard:
        title = company.name or company.legal_name or company.symbol or "公司档案"
        subtitle = " · ".join(
            value
            for value in [
                company.symbol,
                company.exchange or company.market,
                company.country or company.jurisdiction,
                company.lei or company.company_number or company.registry_number,
            ]
            if value
        )
        card = SectionCard()
        top = QHBoxLayout()
        title_box = QVBoxLayout()
        heading = QLabel(title)
        heading.setObjectName("HeroTitle")
        heading.setWordWrap(True)
        meta = QLabel(subtitle or "公开来源返回的公司资料")
        meta.setObjectName("MutedText")
        meta.setWordWrap(True)
        title_box.addWidget(heading)
        title_box.addWidget(meta)
        top.addLayout(title_box, 1)
        top.addWidget(StatusBadge(company.provider or "公开来源", "info"))
        top.addWidget(StatusBadge(self._company_type(company), "success"))
        card.layout.addLayout(top)

        actions = QHBoxLayout()
        add_btn = QPushButton("已在自选" if self.watchlist.contains(company) else "添加自选")
        add_btn.setObjectName("PrimaryButton")
        add_btn.setEnabled(not self.watchlist.contains(company))
        add_btn.clicked.connect(lambda _checked=False, c=company: self._add_watchlist(c))
        back_btn = QPushButton("返回搜索")
        back_btn.clicked.connect(lambda: self.navigate("/search"))
        actions.addWidget(add_btn)
        actions.addWidget(back_btn)
        if company.source_url:
            open_btn = QPushButton("打开来源")
            open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(company.source_url)))
            actions.addWidget(open_btn)
        actions.addStretch()
        if company.updated_at:
            actions.addWidget(StatusBadge(f"更新：{company.updated_at}", "neutral"))
        card.layout.addLayout(actions)
        return card

    def _summary_cards(self, company: CompanyResult) -> QWidget:
        return metric_grid(
            [
                MetricCard("公司类型", self._company_type(company), "根据当前返回字段判断"),
                MetricCard("市场信息", company.exchange or company.market or "暂无数据", "缺失字段不填 0"),
                MetricCard("注册信息", company.jurisdiction or company.country or "暂无数据", company.lei or company.company_number or "暂无注册标识"),
                MetricCard("新闻状态", "加载中" if company.name or company.symbol else "暂无数据", "来自已配置的新闻 provider"),
            ],
            columns=4,
        )

    def _tabs(self, company: CompanyResult) -> QTabWidget:
        tabs = QTabWidget()
        tabs.addTab(self._overview_tab(company), "概览")
        tabs.addTab(self._securities_tab(company), "证券信息")
        tabs.addTab(self._registry_tab(company), "法人注册")
        self.news_tab = QWidget()
        self.news_layout = QVBoxLayout(self.news_tab)
        self.news_layout.setContentsMargins(0, 12, 0, 0)
        self.news_layout.addWidget(LoadingState("正在加载相关新闻..."))
        tabs.addTab(self.news_tab, "新闻动态")
        self.source_tab = QWidget()
        self.source_layout = QVBoxLayout(self.source_tab)
        self.source_layout.setContentsMargins(0, 12, 0, 0)
        self.source_layout.addWidget(SectionCard("数据来源", "搜索完成后会在这里显示 provider 状态、缓存和局部错误。"))
        tabs.addTab(self.source_tab, "数据来源")
        return tabs

    def _overview_tab(self, company: CompanyResult) -> QWidget:
        page = self._tab_page()
        card = SectionCard("公司概览", "只展示公开来源返回的字段，缺失字段显示“暂无数据”。")
        card.layout.addWidget(
            DetailGrid(
                [
                    ("名称", company.name),
                    ("Legal name", company.legal_name),
                    ("简介", company.description),
                    ("官网", company.website),
                    ("国家 / 地区", company.country or company.jurisdiction),
                    ("数据来源", company.provider),
                ],
                columns=2,
            )
        )
        page.layout().addWidget(card)
        page.layout().addStretch()
        return page

    def _securities_tab(self, company: CompanyResult) -> QWidget:
        page = self._tab_page()
        card = SectionCard("证券信息", "只显示 provider 返回的真实字段；当前版本不生成行情、估值或投资建议。")
        card.layout.addWidget(
            DetailGrid(
                [
                    ("Symbol", company.symbol),
                    ("Exchange", company.exchange),
                    ("Market", company.market),
                    ("Currency", str(company.raw.get("currency") or "")),
                    ("Price", str(company.raw.get("price") or "")),
                    ("Market cap", str(company.raw.get("mktCap") or company.raw.get("marketCap") or "")),
                    ("Provider", company.provider),
                    ("Updated at", company.updated_at),
                ],
                columns=2,
            )
        )
        if not (company.symbol or company.exchange or company.market):
            card.layout.addWidget(EmptyState("当前数据源未提供证券信息", "可以尝试配置 FMP、Alpha Vantage 等免费 API key 提升覆盖。"))
        page.layout().addWidget(card)
        page.layout().addStretch()
        return page

    def _registry_tab(self, company: CompanyResult) -> QWidget:
        page = self._tab_page()
        card = SectionCard("法人注册", "注册信息来自 GLEIF、OpenCorporates、Companies House、BRREG 等公开来源或免费 API。")
        card.layout.addWidget(
            DetailGrid(
                [
                    ("Legal name", company.legal_name or company.name),
                    ("Registry number", company.company_number or company.registry_number),
                    ("LEI", company.lei),
                    ("Jurisdiction", company.jurisdiction),
                    ("Status", str(company.raw.get("status") or company.raw.get("entity_status") or "")),
                    ("Registered address", str(company.raw.get("address") or company.raw.get("registered_address") or "")),
                    ("Source provider", company.provider),
                    ("Source URL", company.source_url),
                ],
                columns=2,
            )
        )
        page.layout().addWidget(card)
        page.layout().addStretch()
        return page

    def _load_related(self) -> None:
        company = self.current_company
        if not company:
            return
        query = company.symbol or company.name
        worker = FunctionWorker(self.service.search, query, 8)
        worker.signals.finished.connect(self._render_related)
        worker.signals.error.connect(self._render_related_error)
        self.thread_pool.start(worker)

    def _render_related(self, result: object) -> None:
        if not isinstance(result, SearchResponse):
            self._render_related_error("详情服务返回未知结果。")
            return
        self._clear_layout(self.news_layout)
        news_card = SectionCard("相关新闻", "只展示标题、来源、时间和链接，不复制新闻全文。")
        if not result.news:
            news_card.layout.addWidget(EmptyState("暂无相关新闻", "已配置的新闻 provider 当前未返回结果。"))
        for news in result.news[:8]:
            item = SectionCard(news.title, f"{news.provider} · {news.source or '未知来源'} · {news.published_at or '暂无时间'}")
            if news.snippet:
                snippet = QLabel(news.snippet[:260])
                snippet.setWordWrap(True)
                snippet.setObjectName("MutedText")
                item.layout.addWidget(snippet)
            if news.url:
                open_btn = QPushButton("打开新闻")
                open_btn.clicked.connect(lambda _checked=False, url=news.url: QDesktopServices.openUrl(QUrl(url)))
                item.layout.addWidget(open_btn)
            news_card.layout.addWidget(item)
        self.news_layout.addWidget(news_card)
        self.news_layout.addStretch()

        self._clear_layout(self.source_layout)
        self.source_layout.addWidget(self._source_status_card(result.statuses, result.from_cache))
        self.source_layout.addStretch()

    def _source_status_card(self, statuses: list[ProviderStatus], from_cache: bool) -> SectionCard:
        card = SectionCard("数据来源状态", "provider 细节集中在这里，避免干扰概览。")
        if from_cache:
            card.layout.addWidget(StatusBadge("当前结果来自本地缓存", "info"))
        for status in statuses:
            row = QHBoxLayout()
            row.addWidget(StatusBadge(status.display_name, "neutral"))
            row.addWidget(StatusBadge(friendly_state_label(status.state), friendly_state_tone(status.state)))
            msg = QLabel(sanitize_error_message(status.message))
            msg.setObjectName("MutedText")
            msg.setWordWrap(True)
            row.addWidget(msg, 1)
            card.layout.addLayout(row)
        return card

    def _render_related_error(self, message: str) -> None:
        self._clear_layout(self.news_layout)
        self.news_layout.addWidget(EmptyState("相关新闻加载失败", sanitize_error_message(message)))
        self._clear_layout(self.source_layout)
        self.source_layout.addWidget(EmptyState("数据源诊断暂不可用", sanitize_error_message(message)))

    def _add_watchlist(self, company: CompanyResult) -> None:
        self.watchlist.add(company)
        QMessageBox.information(self, "自选公司", "已保存到本机自选公司。")
        self.refresh()

    def _company_type(self, company: CompanyResult) -> str:
        if company.symbol or company.exchange or company.market:
            return "上市公司"
        if company.lei or company.company_number or company.registry_number:
            return "法人实体"
        return "公开资料"

    def _tab_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)
        return page

    def _clear(self) -> None:
        self._clear_layout(self.layout)

    def _clear_layout(self, layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget:
                widget.deleteLater()
            elif child_layout:
                self._clear_layout(child_layout)
