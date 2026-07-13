from __future__ import annotations

import threading
from collections.abc import Callable

from PySide6.QtCore import Qt, QThreadPool, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api import CompanyNewsService, CompanyProfileService
from cdm_desktop.public_api.crawlergo_provider import CrawlergoWebEvidenceProvider
from cdm_desktop.public_api.data_quality import is_meaningful_value
from cdm_desktop.public_api.models import CompanyProfile, CompanyResult, NewsItem, ProviderStatus
from cdm_desktop.public_api.settings_store import PublicApiSettingsStore
from cdm_desktop.public_api.watchlist_store import WatchlistStore
from cdm_desktop.public_api.web_evidence_models import CrawlResult, WebEvidenceItem
from cdm_desktop.public_api.xueqiu_external_link import build_xueqiu_external_link
from cdm_desktop.ui.components import (
    CollapsibleSection,
    CompanyAvatar,
    DetailGrid,
    EmptyState,
    LoadingState,
    MetricCell,
    NewsRow,
    PageHeader,
    SectionCard,
    StatusBadge,
    friendly_state_label,
    friendly_state_tone,
    sanitize_error_message,
    scroll_container,
)
from cdm_desktop.ui.widgets import FunctionWorker, ProgressFunctionWorker


class CompanyDetailPage(QWidget):
    route = "/company/placeholder"
    page_title = "公司档案"

    def __init__(self, navigate: Callable[[str], None], paths: AppPaths | None = None) -> None:
        super().__init__()
        self.navigate = navigate
        self.paths = paths
        self.current_company: CompanyResult | None = None
        self.profile_service = CompanyProfileService(paths)
        self.news_service = CompanyNewsService(paths)
        self.watchlist = WatchlistStore(paths)
        self.settings_store = PublicApiSettingsStore(paths)
        self.thread_pool = QThreadPool(self)
        self.thread_pool.setMaxThreadCount(3)
        self._active_workers: set[FunctionWorker] = set()
        self.web_crawl_cancel_event: threading.Event | None = None
        self._profile_statuses: list[ProviderStatus] = []
        self._news_statuses: list[ProviderStatus] = []
        self._loaded_profile: CompanyProfile | None = None
        self._detail_request_id = 0
        self._accepting_results = True

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.scroll, _content, self.layout = scroll_container()
        root.addWidget(self.scroll)
        self.refresh()

    def set_company(self, company: CompanyResult) -> None:
        self.current_company = company

    def refresh(self) -> None:
        self._detail_request_id += 1
        request_id = self._detail_request_id
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

        immediate = self.profile_service.get_immediate_profile(company)
        self._loaded_profile = immediate
        self.current_company = _company_from_profile(company, immediate)
        company = self.current_company or company

        self.profile_phase_label = QLabel("已获取本地资料，正在补充公开资料...")
        self.profile_phase_label.setObjectName("MutedText")
        self.layout.addWidget(self.profile_phase_label)
        self.header_host = self._widget_host(self._company_header(company))
        self.summary_host = self._widget_host(self._summary_cards(company))
        self.layout.addWidget(self.header_host)
        self.layout.addWidget(self.summary_host)
        self.tabs = self._tabs(company)
        self.layout.addWidget(self.tabs)
        self._load_related(request_id)
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
        top.setSpacing(14)
        top.addWidget(CompanyAvatar(title))
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
        top.addWidget(StatusBadge(self._company_type(company), "success"))
        add_btn = QPushButton("已在自选" if self.watchlist.contains(company) else "添加自选")
        add_btn.setObjectName("PrimaryButton")
        add_btn.setEnabled(not self.watchlist.contains(company))
        add_btn.clicked.connect(lambda _checked=False, c=company: self._add_watchlist(c))
        top.addWidget(add_btn)
        if company.website:
            open_btn = QPushButton("打开官网")
            open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(company.website)))
            top.addWidget(open_btn)
        card.layout.addLayout(top)
        if company.description:
            description = QLabel(company.description[:280])
            description.setObjectName("MutedText")
            description.setWordWrap(True)
            card.layout.addWidget(description)
        if company.updated_at:
            updated = QLabel(f"数据更新于 {company.updated_at}")
            updated.setObjectName("Caption")
            card.layout.addWidget(updated)
        return card

    def _summary_cards(self, company: CompanyResult) -> QWidget:
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 6, 0, 6)
        row.setSpacing(18)
        values = [
            ("类型", self._company_type(company)),
            ("市场", company.exchange or company.market),
            ("行业", str(company.raw.get("industry") or company.raw.get("sector") or "")),
            ("国家 / 地区", company.country or company.jurisdiction),
            ("注册状态", str(company.raw.get("status") or company.raw.get("entity_status") or "")),
            ("价格", _price_label(company.raw)),
            ("市值", _market_cap_label(company.raw)),
        ]
        for label, value in values:
            if is_meaningful_value(value, "price" if label == "价格" else ""):
                row.addWidget(MetricCell(label, value), 1)
        row.addStretch()
        return host

    def _tabs(self, company: CompanyResult) -> QTabWidget:
        tabs = QTabWidget()
        tabs.addTab(self._overview_tab(company), "概览")
        self.news_tab = QWidget()
        self.news_layout = QVBoxLayout(self.news_tab)
        self.news_layout.setContentsMargins(0, 12, 0, 0)
        self.news_layout.addWidget(LoadingState("正在加载相关新闻..."))
        tabs.addTab(self.news_tab, "新闻")
        tabs.addTab(self._registry_tab(company), "注册信息")
        self.source_tab = QWidget()
        self.source_layout = QVBoxLayout(self.source_tab)
        self.source_layout.setContentsMargins(0, 12, 0, 0)
        self.source_layout.addWidget(SectionCard("数据来源", "搜索完成后会在这里显示 provider 状态、缓存和局部错误。"))
        tabs.addTab(self.source_tab, "来源")
        tabs.addTab(self._securities_tab(company), "证券信息")
        self.web_info_tab = self._web_info_tab(company)
        tabs.addTab(self.web_info_tab, "网页证据")
        return tabs

    def _overview_tab(self, company: CompanyResult) -> QWidget:
        page = self._tab_page()
        fields = _meaningful_fields(
            [
                ("名称", company.name),
                ("法人名称", company.legal_name),
                ("简称", str(company.raw.get("short_name") or "")),
                ("简介", company.description),
                ("官网", company.website),
                ("国家 / 地区", company.country or company.jurisdiction),
                ("板块", str(company.raw.get("sector") or "")),
                ("行业", str(company.raw.get("industry") or "")),
                ("业务范围", str(company.raw.get("business_scope") or "")),
                ("别名", "、".join(company.aliases)),
            ]
        )
        if fields:
            card = SectionCard("公司概览", "只展示当前公开来源成功返回的字段。")
            card.layout.addWidget(DetailGrid(fields, columns=2))
            page.layout().addWidget(card)
        else:
            page.layout().addWidget(EmptyState("暂无公司概览", "当前公开来源暂未返回公司简介或分类资料。"))
        page.layout().addStretch()
        return page

    def _securities_tab(self, company: CompanyResult) -> QWidget:
        page = self._tab_page()
        fields = _meaningful_fields(
            [
                ("股票代码", company.symbol),
                ("交易所", company.exchange),
                ("市场", company.market),
                ("币种", str(company.raw.get("currency") or "")),
                ("证券类型", str(company.raw.get("instrument_type") or "")),
                ("上市日期", str(company.raw.get("listing_date") or company.raw.get("ipo_date") or "")),
                ("价格", _price_label(company.raw)),
                ("市值", _market_cap_label(company.raw)),
                ("更新时间", company.updated_at),
            ]
        )
        if fields:
            card = SectionCard("证券信息", "仅展示可靠来源返回的真实字段；没有实时来源时隐藏价格和市值。")
            card.layout.addWidget(DetailGrid(fields, columns=2))
            page.layout().addWidget(card)
        else:
            page.layout().addWidget(EmptyState("暂无证券信息", "当前数据源未提供可验证的证券资料。"))
        page.layout().addStretch()
        return page

    def _registry_tab(self, company: CompanyResult) -> QWidget:
        page = self._tab_page()
        fields = _meaningful_fields(
            [
                ("法人名称", company.legal_name),
                ("注册号", company.company_number or company.registry_number),
                ("LEI", company.lei),
                ("司法辖区", company.jurisdiction),
                ("注册状态", str(company.raw.get("registration_status") or "")),
                ("实体状态", str(company.raw.get("entity_status") or "")),
                ("注册地址", str(company.raw.get("legal_address") or company.raw.get("registered_address") or "")),
            ]
        )
        if fields:
            card = SectionCard("法人注册", "法人信息来自 GLEIF 或其他公开注册来源。")
            card.layout.addWidget(DetailGrid(fields, columns=2))
            page.layout().addWidget(card)
        else:
            page.layout().addWidget(EmptyState("暂无法人注册资料", "当前公开来源暂未返回法人注册资料。"))
        page.layout().addStretch()
        return page

    def _load_related(self, request_id: int | None = None) -> None:
        company = self.current_company
        if not company:
            return
        request_id = request_id if request_id is not None else self._detail_request_id
        self._profile_statuses = []
        self._news_statuses = []
        profile_worker = FunctionWorker(self.profile_service.get_profile, company)
        self._start_worker(
            profile_worker,
            lambda result, rid=request_id: self._handle_profile_result(rid, result),
            lambda message, rid=request_id: self._handle_profile_error(rid, message),
        )

        news_worker = FunctionWorker(self.news_service.get_news, company, 12)
        self._start_worker(
            news_worker,
            lambda result, rid=request_id: self._handle_news_result(rid, result),
            lambda message, rid=request_id: self._handle_news_error(rid, message),
        )

    def _start_worker(
        self,
        worker: FunctionWorker,
        on_finished: Callable[[object], None],
        on_error: Callable[[str], None],
    ) -> None:
        # Keep the runnable alive until its queued UI-thread callback completes.
        worker.setAutoDelete(False)
        self._active_workers.add(worker)

        def finish(result: object) -> None:
            try:
                on_finished(result)
            finally:
                self._active_workers.discard(worker)

        def fail(message: str) -> None:
            try:
                on_error(message)
            finally:
                self._active_workers.discard(worker)

        worker.signals.finished.connect(finish)
        worker.signals.error.connect(fail)
        self.thread_pool.start(worker)

    def _is_current_request(self, request_id: int) -> bool:
        return self._accepting_results and request_id == self._detail_request_id

    def _handle_profile_result(self, request_id: int, result: object) -> None:
        if self._is_current_request(request_id):
            self._render_profile_result(result)

    def _handle_profile_error(self, request_id: int, message: str) -> None:
        if self._is_current_request(request_id):
            self._render_profile_error(message)

    def _handle_news_result(self, request_id: int, result: object) -> None:
        if self._is_current_request(request_id):
            self._render_news_result(result)

    def _handle_news_error(self, request_id: int, message: str) -> None:
        if self._is_current_request(request_id):
            self._render_news_error(message)

    def _retry_news(self) -> None:
        company = self.current_company
        if not company:
            return
        request_id = self._detail_request_id
        self._clear_layout(self.news_layout)
        self.news_layout.addWidget(LoadingState("正在重新加载相关新闻..."))
        worker = FunctionWorker(self.news_service.get_news, company, 12)
        self._start_worker(
            worker,
            lambda result, rid=request_id: self._handle_news_result(rid, result),
            lambda message, rid=request_id: self._handle_news_error(rid, message),
        )

    def shutdown(self, wait_ms: int = 500) -> bool:
        self._accepting_results = False
        self._detail_request_id += 1
        if self.web_crawl_cancel_event:
            self.web_crawl_cancel_event.set()
        self.thread_pool.clear()
        stopped = self.thread_pool.waitForDone(wait_ms)
        if stopped:
            self._active_workers.clear()
        return stopped

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt override
        self.shutdown()
        super().closeEvent(event)

    def _render_profile_result(self, result: object) -> None:
        if not isinstance(result, tuple) or len(result) != 2:
            self._render_profile_error("详情服务返回未知结果。")
            return
        profile, statuses = result
        self._profile_statuses = list(statuses)
        if isinstance(profile, CompanyProfile):
            self._loaded_profile = profile
            self.current_company = _company_from_profile(self.current_company, profile)
            self._rerender_profile_sections()
            coverage = profile.data_coverage.get("coverage_percent", 0)
            self.profile_phase_label.setText(f"资料补充完成 · 当前字段覆盖 {coverage}%")
        self._refresh_source_status()

    def _rerender_profile_sections(self) -> None:
        company = self.current_company
        if not company:
            return
        current_tab = self.tabs.currentIndex()
        scroll_value = self.scroll.verticalScrollBar().value()
        self._replace_host(self.header_host, self._company_header(company))
        self._replace_host(self.summary_host, self._summary_cards(company))
        self._replace_tab(4, self._securities_tab(company), "证券信息")
        self._replace_tab(2, self._registry_tab(company), "注册信息")
        self._replace_tab(0, self._overview_tab(company), "概览")
        self.tabs.setCurrentIndex(min(current_tab, self.tabs.count() - 1))
        self.scroll.verticalScrollBar().setValue(scroll_value)
        if hasattr(self, "web_evidence_url") and not self.web_evidence_url.text().strip() and company.website:
            self.web_evidence_url.setText(company.website)

    def _replace_tab(self, index: int, page: QWidget, label: str) -> None:
        old = self.tabs.widget(index)
        self.tabs.removeTab(index)
        self.tabs.insertTab(index, page, label)
        if old:
            old.hide()
            old.setParent(None)
            old.deleteLater()

    @staticmethod
    def _widget_host(widget: QWidget) -> QWidget:
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget)
        return host

    def _replace_host(self, host: QWidget, widget: QWidget) -> None:
        layout = host.layout()
        if layout:
            self._clear_layout(layout)
            layout.addWidget(widget)

    def _render_news_result(self, result: object) -> None:
        if not isinstance(result, tuple) or len(result) != 2:
            self._render_news_error("新闻服务返回未知结果。")
            return
        news_items, statuses = result
        self._news_statuses = list(statuses)
        self._clear_layout(self.news_layout)
        news_card = SectionCard("相关新闻")
        if not news_items:
            news_card.layout.addWidget(EmptyState("暂无相关新闻", "当前公开来源暂未返回相关新闻。"))
        for news in list(news_items)[:8]:
            meta = f"{news.source or '未知来源'} · {news.published_at or '暂无时间'}"
            if news.from_cache:
                meta += " · 来自缓存"
            news_card.layout.addWidget(
                NewsRow(
                    news.title,
                    meta,
                    news.snippet,
                    open_action=(lambda url=news.url: QDesktopServices.openUrl(QUrl(url))) if news.url else None,
                )
            )
        self.news_layout.addWidget(news_card)
        if self.current_company:
            self.news_layout.addWidget(self._xueqiu_external_link_card(self.current_company))
        self.news_layout.addStretch()
        self._refresh_source_status()

    def _refresh_source_status(self) -> None:
        self._clear_layout(self.source_layout)
        if self._loaded_profile:
            self.source_layout.addWidget(self._profile_result_card(self._loaded_profile))
        self.source_layout.addWidget(
            self._source_status_card(
                [*self._profile_statuses, *self._news_statuses],
                bool(self._loaded_profile and self._loaded_profile.from_cache),
            )
        )
        self.source_layout.addStretch()

    def _render_profile_error(self, message: str) -> None:
        self._profile_statuses = [
            ProviderStatus("profile", "公司资料", "fallback", "failed", sanitize_error_message(message))
        ]
        if hasattr(self, "profile_phase_label"):
            self.profile_phase_label.setText("公开资料补充失败，已保留本地资料。")
        self._refresh_source_status()

    def _render_news_error(self, message: str) -> None:
        self._clear_layout(self.news_layout)
        self.news_layout.addWidget(
            EmptyState("新闻加载失败", sanitize_error_message(message), action_text="重试", action=self._retry_news)
        )
        self._news_statuses = [
            ProviderStatus("news", "相关新闻", "news", "failed", sanitize_error_message(message))
        ]
        self._refresh_source_status()

    def _load_company_data(
        self,
        company: CompanyResult,
    ) -> tuple[CompanyProfile | None, list[ProviderStatus], list[NewsItem], list[ProviderStatus]]:
        profile, profile_statuses = self.profile_service.get_profile(company)
        news, news_statuses = self.news_service.get_news(company, limit=12)
        return profile, profile_statuses, news, news_statuses

    def _render_related(self, result: object) -> None:
        if not isinstance(result, tuple) or len(result) != 4:
            self._render_related_error("详情服务返回未知结果。")
            return
        profile, profile_statuses, news_items, news_statuses = result
        if isinstance(profile, CompanyProfile):
            self.current_company = _company_from_profile(self.current_company, profile)
        self._clear_layout(self.news_layout)
        news_card = SectionCard("相关新闻")
        if not news_items:
            news_card.layout.addWidget(EmptyState("暂无相关新闻", "已配置的新闻 provider 当前未返回结果。"))
        for news in news_items[:8]:
            meta = f"{news.source or '未知来源'} · {news.published_at or '暂无时间'}"
            if news.from_cache:
                meta += " · 来自缓存"
            news_card.layout.addWidget(
                NewsRow(
                    news.title,
                    meta,
                    news.snippet,
                    open_action=(lambda url=news.url: QDesktopServices.openUrl(QUrl(url))) if news.url else None,
                )
            )
        self.news_layout.addWidget(news_card)
        if self.current_company:
            self.news_layout.addWidget(self._xueqiu_external_link_card(self.current_company))
        self.news_layout.addStretch()

        self._clear_layout(self.source_layout)
        if isinstance(profile, CompanyProfile):
            self.source_layout.addWidget(self._profile_result_card(profile))
        self.source_layout.addWidget(self._source_status_card([*profile_statuses, *news_statuses], bool(profile and profile.from_cache)))
        self.source_layout.addStretch()

    def _profile_result_card(self, profile: CompanyProfile) -> SectionCard:
        card = SectionCard("已获取的公司详情字段", "这里只展示 provider 真实返回并成功合并的字段。")
        if profile.from_cache:
            card.layout.addWidget(StatusBadge("来自缓存", "info"))
        coverage = profile.data_coverage
        if coverage:
            card.layout.addWidget(
                QLabel(
                    f"资料完整度 {coverage.get('coverage_percent', 0)}% · "
                    f"已填充 {coverage.get('populated_fields', 0)}/{coverage.get('total_supported_fields', 0)} 个适用字段"
                )
            )
        if profile.updated_at:
            updated = QLabel(f"资料更新时间：{profile.updated_at}")
            updated.setObjectName("MutedText")
            card.layout.addWidget(updated)
        source_counts: dict[str, int] = {}
        for source in profile.field_sources.values():
            source_counts[source] = source_counts.get(source, 0) + 1
        for source, count in sorted(source_counts.items()):
            source_row = QLabel(f"{source} · 成功字段 {count}")
            source_row.setObjectName("MutedText")
            card.layout.addWidget(source_row)
        if profile.missing_fields:
            missing = QLabel(f"当前适用字段中未返回 {len(profile.missing_fields)} 个")
            missing.setObjectName("MutedText")
            card.layout.addWidget(missing)
        fields = _meaningful_fields(
            [
                    ("Display name", profile.display_name),
                    ("Legal name", profile.legal_name),
                    ("Symbol", profile.symbol),
                    ("Exchange", profile.exchange),
                    ("Country", profile.country),
                    ("Sector", profile.sector),
                    ("Industry", profile.industry),
                    ("Website", profile.website),
                    ("Price", profile.price),
                    ("Market cap", profile.market_cap),
                    ("Currency", profile.currency),
                    ("CEO", profile.ceo),
                    ("Employees", profile.employees),
                    ("Wikidata", profile.wikidata_id),
                    ("Wikipedia", profile.wikipedia_url),
                ]
        )
        if fields:
            card.layout.addWidget(DetailGrid(fields, columns=2))
        return card

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

    def _web_info_tab(self, company: CompanyResult) -> QWidget:
        page = self._tab_page()
        policy = self.settings_store.crawlergo_policy()
        provider = CrawlergoWebEvidenceProvider(crawlergo_path=self.settings_store.crawlergo_path())
        state, message = provider.dependency_status()
        website = company.website or str(company.raw.get("website") or company.source_url or "")

        control = SectionCard(
            "网页证据采集",
            "用于采集公司官网或授权公开页面的元数据和短摘录。尊重 robots.txt，不绕过登录/验证码；雪球仅作为外部入口。",
        )
        control.layout.addWidget(StatusBadge(friendly_state_label(state), friendly_state_tone(state)))
        control.layout.addWidget(QLabel(sanitize_error_message(message)))
        input_row = QHBoxLayout()
        self.web_evidence_url = QLineEdit()
        self.web_evidence_url.setPlaceholderText("添加公司官网 / IR 页面 URL，例如 https://example.com/investors")
        self.web_evidence_url.setText(website)
        crawl_btn = QPushButton("补充官网资料")
        crawl_btn.setObjectName("PrimaryButton")
        crawl_btn.clicked.connect(self._start_web_evidence_crawl)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self._cancel_web_evidence_crawl)
        input_row.addWidget(QLabel("URL"))
        input_row.addWidget(self.web_evidence_url, 1)
        input_row.addWidget(crawl_btn)
        input_row.addWidget(cancel_btn)
        control.layout.addLayout(input_row)

        self.web_evidence_progress = QProgressBar()
        self.web_evidence_progress.setRange(0, 1)
        self.web_evidence_progress.setValue(0)
        self.web_evidence_status = QLabel(
            f"robots 合规已开启。默认最大 {policy.max_pages_per_domain} 页，最大深度 {policy.max_depth}。"
        )
        self.web_evidence_status.setObjectName("MutedText")
        self.web_evidence_status.setWordWrap(True)
        control.layout.addWidget(self.web_evidence_progress)
        control.layout.addWidget(self.web_evidence_status)
        page.layout().addWidget(control)

        self.web_evidence_list = QVBoxLayout()
        self.web_evidence_list.setSpacing(10)
        list_host = SectionCard("网页证据列表", "默认只显示标题、类型、短摘录、采集时间和原文链接。")
        list_host.layout.addLayout(self.web_evidence_list)
        self.web_evidence_list.addWidget(EmptyState("暂无网页证据", "配置 crawlergo 路径后，可手动采集公司官网公开页面。"))
        page.layout().addWidget(list_host)

        self.web_evidence_diag = QVBoxLayout()
        diagnostics = CollapsibleSection("采集诊断", "显示 discovered URLs、skipped URLs、robots blocked、timeout 和 parse error。", expanded=False)
        diagnostics.body_layout.addLayout(self.web_evidence_diag)
        self.web_evidence_diag.addWidget(QLabel("尚未执行采集。"))
        page.layout().addWidget(diagnostics)
        page.layout().addStretch()
        return page

    def _start_web_evidence_crawl(self) -> None:
        company = self.current_company
        if not company:
            return
        url = self.web_evidence_url.text().strip()
        if not url:
            QMessageBox.information(self, "网页证据采集", "请先输入公司官网或 IR 页面 URL。")
            return
        self.web_crawl_cancel_event = threading.Event()
        self.web_evidence_progress.setRange(0, 1)
        self.web_evidence_progress.setValue(0)
        self.web_evidence_status.setText("正在准备采集...")
        self._clear_layout(self.web_evidence_list)
        self.web_evidence_list.addWidget(LoadingState("正在采集网页证据..."))
        worker = ProgressFunctionWorker(self._run_web_evidence_crawl, company, url)
        worker.signals.progress.connect(self._update_web_evidence_progress)
        self._start_worker(worker, self._render_web_evidence_result, self._render_web_evidence_error)

    def _cancel_web_evidence_crawl(self) -> None:
        if self.web_crawl_cancel_event:
            self.web_crawl_cancel_event.set()
            self.web_evidence_status.setText("已请求取消，当前页面处理完成后停止。")

    def _run_web_evidence_crawl(
        self,
        company: CompanyResult,
        url: str,
        *,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> CrawlResult:
        provider = CrawlergoWebEvidenceProvider(crawlergo_path=self.settings_store.crawlergo_path())
        policy = self.settings_store.crawlergo_policy()
        return provider.crawl(
            company_name=company.name or company.display_name or company.symbol or "",
            seed_urls=[url],
            policy=policy,
            progress_callback=progress_callback,
            cancel_event=self.web_crawl_cancel_event,
        )

    def _update_web_evidence_progress(self, current: int, total: int, message: str) -> None:
        self.web_evidence_progress.setRange(0, max(total, 1))
        self.web_evidence_progress.setValue(max(0, min(current, max(total, 1))))
        self.web_evidence_status.setText(sanitize_error_message(message))

    def _render_web_evidence_result(self, result: object) -> None:
        self._clear_layout(self.web_evidence_list)
        self._clear_layout(self.web_evidence_diag)
        if not isinstance(result, CrawlResult):
            self._render_web_evidence_error("网页证据采集返回未知结果。")
            return
        self.web_evidence_progress.setRange(0, max(result.job.pages_discovered, 1))
        self.web_evidence_progress.setValue(result.job.pages_crawled)
        self.web_evidence_status.setText(
            f"采集完成：发现 {result.job.pages_discovered}，采集 {result.job.pages_crawled}，跳过 {result.job.pages_skipped}。"
        )
        if result.error_message:
            self.web_evidence_list.addWidget(EmptyState("网页证据采集不可用", sanitize_error_message(result.error_message)))
        elif not result.items:
            self.web_evidence_list.addWidget(EmptyState("没有可展示的网页证据", "目标页面可能被 robots.txt 禁止、超时或未返回可提取内容。"))
        for item in result.items:
            self.web_evidence_list.addWidget(self._web_evidence_card(item))
        for url in result.discovered_urls[:20]:
            self.web_evidence_diag.addWidget(QLabel(f"发现：{url}"))
        for skipped in result.skipped_urls[:20]:
            self.web_evidence_diag.addWidget(QLabel(f"跳过：{skipped.get('url', '')} · {sanitize_error_message(skipped.get('reason', ''))}"))
        for diagnostic in result.diagnostics[:20]:
            self.web_evidence_diag.addWidget(QLabel(sanitize_error_message(diagnostic)))
        if not (result.discovered_urls or result.skipped_urls or result.diagnostics):
            self.web_evidence_diag.addWidget(QLabel("无诊断信息。"))

    def _web_evidence_card(self, item: WebEvidenceItem) -> SectionCard:
        card = SectionCard(item.title or item.final_url or item.source_url, f"{item.domain} · {item.content_type} · {item.crawled_at}")
        badge_row = QHBoxLayout()
        badge_row.addWidget(StatusBadge("robots allowed" if item.robots_allowed else "robots blocked", "success" if item.robots_allowed else "danger"))
        if item.from_cache:
            badge_row.addWidget(StatusBadge("from_cache", "info"))
        badge_row.addStretch()
        card.layout.addLayout(badge_row)
        snippet = QLabel(item.content_snippet or item.description or item.extracted_text_preview or "暂无短摘录。")
        snippet.setObjectName("MutedText")
        snippet.setWordWrap(True)
        card.layout.addWidget(snippet)
        open_btn = QPushButton("打开原文")
        open_btn.clicked.connect(lambda _checked=False, url=item.open_url or item.final_url: QDesktopServices.openUrl(QUrl(url)))
        card.layout.addWidget(open_btn)
        return card

    def _render_web_evidence_error(self, message: str) -> None:
        self._clear_layout(self.web_evidence_list)
        self.web_evidence_list.addWidget(EmptyState("网页证据采集失败", sanitize_error_message(message)))
        self.web_evidence_status.setText(sanitize_error_message(message))

    def _xueqiu_external_link_card(self, company: CompanyResult) -> SectionCard:
        link = build_xueqiu_external_link(
            symbol=company.symbol,
            exchange=company.exchange,
            market=company.market,
            company_name=company.name or company.display_name or company.legal_name,
        )
        card = SectionCard(
            "雪球社区入口",
            "可在雪球查看该公司的投资者讨论、行情页面和社区动态。本应用仅提供外部链接，不抓取、不缓存、不总结雪球内容。",
        )
        badge_row = QHBoxLayout()
        badge_row.addWidget(StatusBadge("外部链接", "info"))
        badge_row.addWidget(StatusBadge("不抓取内容", "warning"))
        badge_row.addStretch()
        card.layout.addLayout(badge_row)

        note = QLabel(link.description if link.is_direct_stock_link else "暂无可直接跳转的雪球股票代码。可手动打开雪球搜索公司名称。")
        note.setObjectName("MutedText")
        note.setWordWrap(True)
        card.layout.addWidget(note)

        action_row = QHBoxLayout()
        open_btn = QPushButton("打开雪球" if link.is_direct_stock_link else "打开雪球首页")
        open_btn.clicked.connect(lambda _checked=False, url=link.url: QDesktopServices.openUrl(QUrl(url)))
        action_row.addWidget(open_btn)
        action_row.addStretch()
        card.layout.addLayout(action_row)
        return card

    def _render_related_error(self, message: str) -> None:
        self._clear_layout(self.news_layout)
        self.news_layout.addWidget(EmptyState("相关新闻加载失败", sanitize_error_message(message)))
        self._clear_layout(self.source_layout)
        self.source_layout.addWidget(EmptyState("数据源诊断暂不可用", sanitize_error_message(message)))

    def _add_watchlist(self, company: CompanyResult) -> None:
        self.watchlist.add(company)
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage("已添加到自选公司", 3000)
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
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        return page

    def _clear(self) -> None:
        self._clear_layout(self.layout)

    def _clear_layout(self, layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
            elif child_layout:
                self._clear_layout(child_layout)


def _company_from_profile(company: CompanyResult | None, profile: CompanyProfile) -> CompanyResult | None:
    if company is None:
        return None
    company.display_name = profile.display_name or company.display_name
    company.name = profile.display_name or company.name
    company.legal_name = profile.legal_name or company.legal_name
    company.aliases = list(dict.fromkeys([*company.aliases, *profile.aliases]))
    company.symbol = profile.symbol or company.symbol
    company.exchange = profile.exchange or company.exchange
    company.market = profile.market or company.market
    company.lei = profile.lei or company.lei
    company.wikidata_id = profile.wikidata_id or company.wikidata_id
    company.wikipedia_url = profile.wikipedia_url or company.wikipedia_url
    company.website = profile.website or company.website
    company.description = profile.description or company.description
    company.country = profile.country or company.country
    company.company_number = profile.company_number or profile.registration_number or company.company_number
    company.registry_number = profile.registry_number or company.registry_number
    company.jurisdiction = profile.jurisdiction or company.jurisdiction
    company.updated_at = profile.updated_at or company.updated_at
    company.raw = {
        **company.raw,
        "short_name": profile.short_name,
        "currency": profile.currency,
        "instrument_type": profile.instrument_type,
        "sector": profile.sector,
        "industry": profile.industry,
        "business_scope": profile.business_scope,
        "price": profile.price,
        "previous_close": profile.previous_close,
        "market_cap": profile.market_cap,
        "listing_date": profile.listing_date,
        "ipo_date": profile.ipo_date,
        "registration_status": profile.registration_status,
        "entity_status": profile.entity_status,
        "legal_address": profile.legal_address,
        "registered_address": profile.registered_address,
        "address": profile.address,
        "provider_sources": profile.provider_sources,
        "field_sources": profile.field_sources,
        "data_coverage": profile.data_coverage,
        "latest_profile": profile.to_dict(),
    }
    company.from_cache = profile.from_cache
    return company


def _meaningful_fields(fields: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(label, value) for label, value in fields if is_meaningful_value(value)]


def _price_label(raw: dict[str, object]) -> str:
    value = raw.get("price")
    if not is_meaningful_value(value, "price"):
        return ""
    currency = str(raw.get("currency") or "").strip()
    return f"{value} {currency}".strip()


def _market_cap_label(raw: dict[str, object]) -> str:
    value = raw.get("market_cap") or raw.get("mktCap") or raw.get("marketCap")
    if not is_meaningful_value(value, "market_cap"):
        return ""
    currency = str(raw.get("currency") or "").strip()
    return f"{value} {currency}".strip()
