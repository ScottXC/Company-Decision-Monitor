from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from PySide6.QtCore import Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api import PublicSearchService, SearchResponse
from cdm_desktop.public_api.models import CompanyResult, NewsItem, ProviderStatus
from cdm_desktop.public_api.query import analyze_query
from cdm_desktop.public_api.search_service import REGION_OPTIONS, region_label
from cdm_desktop.public_api.watchlist_store import WatchlistStore
from cdm_desktop.ui.components import (
    CollapsibleSection,
    EmptyState,
    InlineError,
    ListRow,
    LoadingState,
    PageHeader,
    SectionCard,
    StatusBadge,
    friendly_state_label,
    friendly_state_tone,
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

DEBOUNCE_MS = 350
MIN_TEXT_QUERY_LENGTH = 2
MAX_SEARCH_WORKER_THREADS = 4

logger = logging.getLogger(__name__)


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
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(MAX_SEARCH_WORKER_THREADS)
        self.search_request_id = 0
        self._accepting_searches = True
        self._active_cancel_event: threading.Event | None = None
        self._visible_company_keys: set[str] = set()
        self._background_status_label: QLabel | None = None
        self.debounce_timer = QTimer(self)
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(DEBOUNCE_MS)
        self.debounce_timer.timeout.connect(self._run_debounced_search)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, self.layout = scroll_container()
        root.addWidget(scroll)

        self.layout.addWidget(
            PageHeader(
                "搜索公司",
                "输入公司名称、股票代码或简称，本地结果会优先显示。",
            )
        )
        self.layout.addWidget(self._search_panel())
        self.result_host = QVBoxLayout()
        self.result_host.setSpacing(8)
        self.side_host = QVBoxLayout()
        self.side_host.setSpacing(8)
        self.layout.addLayout(self.result_host)
        self.layout.addLayout(self.side_host)
        self._show_initial_state()
        self.layout.addStretch()

    def set_query(self, keyword: str) -> None:
        self.input.setText(keyword)
        self.input.setFocus()

    def run_search(self) -> None:
        self.debounce_timer.stop()
        self._start_search()

    def _start_search(self) -> None:
        if not self._accepting_searches:
            return
        keyword = self.input.text().strip()
        if self._active_cancel_event:
            self._active_cancel_event.set()
        self.thread_pool.clear()
        cancel_event = threading.Event()
        self._active_cancel_event = cancel_event
        self.search_request_id += 1
        request_id = self.search_request_id
        self._clear_results()
        if not keyword:
            self._show_initial_state()
            return
        self.cancel_btn.setEnabled(True)
        self.result_host.addWidget(
            LoadingState(
                f"正在按“{region_label(self.current_region)}”查询本地开源索引。"
                "首批结果显示后再后台补充公开数据。"
            )
        )
        worker = FunctionWorker(
            self._run_local_search,
            request_id,
            keyword,
            self.current_region,
            self.current_scope,
            cancel_event,
        )
        worker.signals.finished.connect(self._render_local_response)
        worker.signals.error.connect(lambda message, rid=request_id: self._render_request_error(rid, message))
        self.thread_pool.start(worker)

    def _on_query_changed(self, text: str) -> None:
        if self._active_cancel_event:
            self._active_cancel_event.set()
        self.search_request_id += 1
        self.debounce_timer.stop()
        cleaned = text.strip()
        if not cleaned:
            return
        info = analyze_query(cleaned)
        if len(cleaned) < MIN_TEXT_QUERY_LENGTH and info.kind == "name":
            return
        self.debounce_timer.start(0 if info.kind != "name" and len(cleaned) >= 2 else DEBOUNCE_MS)

    def _run_debounced_search(self) -> None:
        self._start_search()

    def _cancel_search(self) -> None:
        if self._active_cancel_event:
            self._active_cancel_event.set()
        self.search_request_id += 1
        self.debounce_timer.stop()
        self.cancel_btn.setEnabled(False)
        if self._background_status_label:
            self._background_status_label.setText("已取消当前搜索；后台返回的旧结果不会更新界面。")

    def _run_local_search(
        self,
        request_id: int,
        keyword: str,
        region: str,
        scope: str,
        cancel_event: threading.Event,
    ) -> tuple[int, SearchResponse]:
        response = self.service.search_local(
            keyword,
            20,
            region_filter=region,
            scope_filter=scope,
            cancel_check=cancel_event.is_set,
        )
        return request_id, response

    def _run_background_enrichment(
        self,
        request_id: int,
        keyword: str,
        region: str,
        scope: str,
        local_response: SearchResponse,
        cancel_event: threading.Event,
    ) -> tuple[int, SearchResponse]:
        response = self.service.enrich_search(
            keyword,
            local_response,
            20,
            region_filter=region,
            scope_filter=scope,
            cancel_check=cancel_event.is_set,
        )
        return request_id, response

    def _render_local_response(self, payload: object) -> None:
        if not isinstance(payload, tuple) or len(payload) != 2:
            self._render_error("本地搜索返回了未知结果。")
            return
        request_id, result = payload
        if request_id != self.search_request_id or not isinstance(result, SearchResponse):
            if isinstance(result, SearchResponse) and result.timing:
                result.timing.cancelled = True
            return
        if result.timing and result.timing.cancelled:
            return
        self._render_response(result)
        self._visible_company_keys = {company.dedupe_key() for company in result.companies}
        self._background_status_label = QLabel("已显示本地开源索引结果，正在后台补充公开数据。")
        self._background_status_label.setObjectName("MutedText")
        self._background_status_label.setWordWrap(True)
        self.side_host.addWidget(self._background_status_label)
        worker = FunctionWorker(
            self._run_background_enrichment,
            request_id,
            result.query,
            self.current_region,
            self.current_scope,
            result,
            self._active_cancel_event or threading.Event(),
        )
        worker.signals.finished.connect(self._render_enrichment_response)
        worker.signals.error.connect(lambda message, rid=request_id: self._render_enrichment_error(rid, message))
        self.thread_pool.start(worker)

    def _render_enrichment_response(self, payload: object) -> None:
        if not isinstance(payload, tuple) or len(payload) != 2:
            return
        request_id, result = payload
        if request_id != self.search_request_id or not isinstance(result, SearchResponse):
            if isinstance(result, SearchResponse) and result.timing:
                result.timing.cancelled = True
            return
        if result.timing and result.timing.cancelled:
            return
        new_rows = [company for company in result.companies if company.dedupe_key() not in self._visible_company_keys]
        if new_rows:
            for company in new_rows:
                self._visible_company_keys.add(company.dedupe_key())
            self.result_host.addWidget(self._company_group("公开数据补充", new_rows))
        if self._background_status_label:
            self._background_status_label.setText("已完成公开数据补充。")
        self.cancel_btn.setEnabled(False)
        self.side_host.addWidget(self._diagnostics(result.statuses))

    def _render_request_error(self, request_id: int, message: str) -> None:
        if request_id == self.search_request_id:
            self._render_error(message)

    def _render_enrichment_error(self, request_id: int, _message: str) -> None:
        if request_id == self.search_request_id and self._background_status_label:
            self._background_status_label.setText("部分公开数据源暂时不可用，已保留本地结果。")

    def _search_panel(self) -> QWidget:
        card = QWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(10)

        region_row = QHBoxLayout()
        region_label_widget = QLabel("地区")
        region_label_widget.setObjectName("MutedText")
        self.region_filter = QComboBox()
        self.region_filter.setMinimumWidth(220)
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
        card_layout.addLayout(region_row)

        search_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setObjectName("HeroSearchInput")
        self.input.setPlaceholderText("搜索公司、股票代码或简称")
        self.input.setClearButtonEnabled(True)
        self.input.returnPressed.connect(self.run_search)
        self.input.textChanged.connect(self._on_query_changed)
        search_btn = QPushButton("搜索")
        search_btn.setObjectName("PrimaryButton")
        search_btn.clicked.connect(self.run_search)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_search)
        search_row.addWidget(self.input, 1)
        search_row.addWidget(search_btn)
        search_row.addWidget(self.cancel_btn)
        card_layout.addLayout(search_row)

        scope_row = QHBoxLayout()
        self.scope_group = QButtonGroup(self)
        self.scope_group.setExclusive(True)
        for label, value in SCOPES:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setObjectName("ScopeChip")
            button.setProperty("scope", value)
            if value == "news":
                button.setEnabled(False)
                button.setToolTip("新闻在公司详情页按需加载，不参与普通公司搜索。")
            if value == "all":
                button.setChecked(True)
            button.clicked.connect(self._scope_changed)
            self.scope_group.addButton(button)
            scope_row.addWidget(button)
        scope_row.addStretch()
        card_layout.addLayout(scope_row)
        return card

    def _scope_changed(self) -> None:
        button = self.sender()
        if isinstance(button, QPushButton):
            if self._active_cancel_event:
                self._active_cancel_event.set()
            self.current_scope = str(button.property("scope"))
            self.search_request_id += 1
            if self.input.text().strip():
                self.debounce_timer.start(DEBOUNCE_MS)

    def _region_changed(self) -> None:
        if self._active_cancel_event:
            self._active_cancel_event.set()
        self.current_region = str(self.region_filter.currentData() or "all")
        self.search_request_id += 1
        self.region_hint.setText(
            str(self.region_filter.itemData(self.region_filter.currentIndex(), Qt.ItemDataRole.ToolTipRole) or "")
        )
        if self.input.text().strip():
            self.debounce_timer.start(DEBOUNCE_MS)

    def _render_response(self, result: object) -> None:
        render_started = time.perf_counter()
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
        self.side_host.addWidget(self._diagnostics(result.statuses))
        if result.timing:
            result.timing.render_ms = (time.perf_counter() - render_started) * 1000
            logger.debug("search_render_timing payload=%s", result.timing.to_dict())

    def _render_light_status(self, statuses: list[ProviderStatus], from_cache: bool) -> None:
        failed = sum(1 for item in statuses if item.state in {"failed", "invalid_key", "rate_limited", "network_timeout"})
        card = QWidget()
        row = QHBoxLayout(card)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(StatusBadge("本地结果", "success"))
        if from_cache:
            row.addWidget(StatusBadge("来自缓存", "info"))
        if failed:
            row.addWidget(StatusBadge("部分公开来源暂时不可用", "warning"))
        row.addStretch()
        self.side_host.addWidget(card)

    def _company_group(self, title: str, companies: list[CompanyResult]) -> SectionCard:
        card = SectionCard(f"{title} · {len(companies)}")
        for company in companies:
            card.layout.addWidget(self._company_card(company))
        return card

    def _company_card(self, company: CompanyResult) -> QWidget:
        identity = company.symbol or company.lei or company.company_number or company.registry_number or "暂无标识"
        region = company.exchange or company.market or company.jurisdiction or company.country or "暂无地区"
        source = "本地索引" if company.provider_id == "symbol_universe" or company.raw.get("from_local_index") else "公开来源"
        row = ListRow(
            company.name or company.display_name or company.legal_name or identity,
            f"{identity} · {region}",
            detail=company.description or self._company_kind(company),
            source=source,
            action_tooltip="添加自选",
            action=lambda c=company: self._add_watchlist(c),
        )
        row.activated.connect(lambda c=company: self._open_detail(c))
        return row

    @staticmethod
    def _company_kind(company: CompanyResult) -> str:
        if company.symbol:
            return "上市公司"
        if company.lei or company.company_number or company.registry_number:
            return "法人实体"
        return "公开公司资料"

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
        best = [item for item in companies if item.match_score >= 85][:3]
        best_keys = {item.dedupe_key() for item in best}
        financial = [
            item
            for item in companies
            if item.dedupe_key() not in best_keys
            and (item.category == "financial" or item.provider_id in {"fmp", "alpha_vantage", "nasdaq_directory"})
        ]
        financial_keys = {item.dedupe_key() for item in financial}
        entity = [
            item
            for item in companies
            if item.dedupe_key() not in best_keys | financial_keys
            and (
                item.category in {"global", "registry"}
                or item.provider_id in {"gleif", "opencorporates", "companies_house", "norway_brreg"}
            )
        ]
        shown_keys = best_keys | financial_keys | {item.dedupe_key() for item in entity}
        related = [item for item in companies if item.dedupe_key() not in shown_keys and item.match_score < 85]
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
            "请尝试使用公司全称、股票代码、英文名、中文简称、注册号或 LEI；高级用户可在设置页启用 API provider 扩展覆盖。",
            action_text="数据源设置",
            action=lambda: self.navigate("/settings"),
        )

    def _add_watchlist(self, company: CompanyResult) -> None:
        self.watchlist.add(company)
        if self.on_watchlist_changed:
            self.on_watchlist_changed()
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage("已添加到自选公司", 3000)

    def _open_detail(self, company: CompanyResult) -> None:
        if self.on_company_selected:
            self.on_company_selected(company)
        else:
            self.navigate("/company/placeholder")

    def _render_error(self, message: str) -> None:
        self.cancel_btn.setEnabled(False)
        self._clear_results()
        self.result_host.addWidget(InlineError(message, retry=self.run_search))

    def _show_initial_state(self) -> None:
        self.result_host.addWidget(
            EmptyState(
                "搜索公司名称、股票代码或简称",
                "本地开源索引会优先返回结果，公开数据随后在后台补充。",
            )
        )

    def _clear_results(self) -> None:
        self._clear_layout(self.result_host)
        self._clear_layout(self.side_host)

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

    def shutdown(self, wait_ms: int = 250) -> bool:
        self._accepting_searches = False
        self.debounce_timer.stop()
        if self._active_cancel_event:
            self._active_cancel_event.set()
        self.thread_pool.clear()
        return self.thread_pool.waitForDone(wait_ms)
