from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop.db import DatabaseManager
from cdm_desktop.paths import AppPaths
from cdm_desktop.search.models import CompanySearchCandidate, OnlineSearchResult, SearchScope
from cdm_desktop.search.online_search_service import OnlineCompanySearchService
from cdm_desktop.services.watchlist_service import WatchlistService
from cdm_desktop.ui.company_detail_dialog import CompanyDetailDialog
from cdm_desktop.ui.widgets import (
    Card,
    EmptyState,
    FunctionWorker,
    TextViewerDialog,
    clear_layout,
    info,
    make_scroll_area,
    warn,
)

SCOPE_ITEMS: tuple[tuple[str, SearchScope], ...] = (
    ("全部", "all"),
    ("美股", "us"),
    ("港股", "hk"),
    ("A股", "a_share"),
    ("公告/披露", "filings"),
    ("新闻/网页", "news"),
)


class OnlineSearchPage(QWidget):
    page_title = "联网搜索"
    primary_action_text = "联网搜索"

    def __init__(
        self,
        db: DatabaseManager,
        paths: AppPaths,
        open_company_callback: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__()
        self.db = db
        self.paths = paths
        self.open_company_callback = open_company_callback
        self.current_scope: SearchScope = "all"
        self.thread_pool = QThreadPool.globalInstance()

        root = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索公司名称、股票代码、简称...")
        self.search_input.returnPressed.connect(self.run_primary_action)
        search_btn = QPushButton("联网搜索")
        search_btn.setObjectName("PrimaryButton")
        search_btn.clicked.connect(self.run_primary_action)
        controls.addWidget(self.search_input, 1)
        controls.addWidget(search_btn)
        root.addLayout(controls)

        scope_row = QHBoxLayout()
        self.scope_group = QButtonGroup(self)
        self.scope_group.setExclusive(True)
        for label, scope in SCOPE_ITEMS:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("scope", scope)
            button.setObjectName("ScopeChip")
            if scope == "all":
                button.setChecked(True)
            self.scope_group.addButton(button)
            scope_row.addWidget(button)
        self.scope_group.buttonClicked.connect(self._scope_changed)
        scope_row.addStretch()
        root.addLayout(scope_row)

        self.status_label = QLabel("SEC / Nasdaq Trader / HKEX / Stock Connect：等待搜索")
        self.status_label.setObjectName("MutedText")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.scroll, _content, self.results_layout = make_scroll_area()
        root.addWidget(self.scroll, 1)
        self._show_empty()

    def set_query(self, query: str) -> None:
        self.search_input.setText(query)
        self.search_input.setFocus()

    def run_primary_action(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            self._show_empty("请输入公司名称、股票代码或简称。")
            return
        self.status_label.setText("正在联网搜索公开来源...")
        clear_layout(self.results_layout)
        self.results_layout.addWidget(EmptyState("正在搜索", "正在查询 SEC、Nasdaq Trader、HKEX 等公开来源。"))
        worker = FunctionWorker(self._search, query, self.current_scope)
        worker.signals.finished.connect(self._search_finished)
        worker.signals.error.connect(self._search_failed)
        self.thread_pool.start(worker)

    def _search(self, query: str, scope: SearchScope) -> OnlineSearchResult:
        with self.db.session() as session:
            return OnlineCompanySearchService(session).search(query, scope)

    def _search_finished(self, result: OnlineSearchResult) -> None:
        clear_layout(self.results_layout)
        status_parts = [
            f"{response.provider_id}: {response.status}" + (f" ({response.error_message})" if response.error_message else "")
            for response in result.provider_responses
        ]
        suffix = " · 使用缓存" if result.from_cache else ""
        self.status_label.setText(("；".join(status_parts) or "无 provider 响应") + suffix)
        if not result.candidates:
            self.results_layout.addWidget(
                EmptyState(
                    "没有找到公司",
                    "当前网络不可用或公开来源没有匹配结果。你仍可查看已加入自选的公司和历史事件。",
                )
            )
            self.results_layout.addStretch()
            return
        current_provider = ""
        for candidate in result.candidates:
            provider = candidate.source_provider or "公开来源"
            if provider != current_provider:
                current_provider = provider
                title = QLabel(provider)
                title.setObjectName("SectionTitle")
                self.results_layout.addWidget(title)
            self.results_layout.addWidget(
                OnlineSearchResultCard(
                    candidate,
                    on_add=lambda item=candidate: self.add_to_watchlist(item),
                    on_source=lambda url=candidate.source_url: self.open_source(url),
                    on_detail=lambda item=candidate: self.open_candidate_detail(item),
                )
            )
        self.results_layout.addStretch()

    def _search_failed(self, message: str) -> None:
        self.status_label.setText("网络异常")
        clear_layout(self.results_layout)
        self.results_layout.addWidget(
            EmptyState(
                "当前网络不可用，无法进行新的联网搜索。",
                "你仍可查看已加入自选的公司和历史事件。",
            )
        )
        warn(self, f"联网搜索失败：\n{message}")

    def add_to_watchlist(self, candidate: CompanySearchCandidate) -> None:
        try:
            with self.db.session() as session:
                result = WatchlistService(session).add_to_watchlist(candidate)
                company_id = result.company_id
        except Exception as exc:
            warn(self, f"加入自选失败：{exc}")
            return
        info(self, "已加入自选公司。")
        if self.open_company_callback:
            self.open_company_callback(company_id)
        else:
            CompanyDetailDialog(self.db, self.paths, company_id, self).exec()

    def open_source(self, url: str) -> None:
        if not url.startswith(("http://", "https://")):
            warn(self, "该结果没有可打开的公开来源 URL。")
            return
        QDesktopServices.openUrl(QUrl(url))

    def open_candidate_detail(self, candidate: CompanySearchCandidate) -> None:
        if candidate.company_id:
            if self.open_company_callback:
                self.open_company_callback(candidate.company_id)
                return
            CompanyDetailDialog(self.db, self.paths, candidate.company_id, self).exec()
            return
        details = [
            f"公司名称：{candidate.name}",
            f"法定名称：{candidate.legal_name or '-'}",
            f"代码：{candidate.ticker or '-'}",
            f"交易所/市场：{' / '.join(item for item in [candidate.exchange, candidate.market] if item) or '-'}",
            f"国家/地区：{candidate.country or '-'}",
            f"行业：{candidate.industry or '-'}",
            f"来源：{candidate.source_provider or '-'}",
            f"来源 URL：{candidate.source_url or '-'}",
            f"匹配原因：{candidate.match_reason or '-'}",
            f"置信度：{int(round(candidate.confidence_score))}",
            f"数据新鲜度：{candidate.freshness or '-'}",
            f"覆盖说明：{candidate.coverage_note or '-'}",
        ]
        if candidate.aliases:
            details.append(f"别名：{', '.join(candidate.aliases)}")
        TextViewerDialog("候选公司详情", "\n".join(details), self).exec()

    def _scope_changed(self, button: QPushButton) -> None:
        self.current_scope = str(button.property("scope"))  # type: ignore[assignment]

    def _show_empty(self, message: str | None = None) -> None:
        clear_layout(self.results_layout)
        self.results_layout.addWidget(
            EmptyState(
                "联网搜索公开公司资料",
                message or "输入公司名称、股票代码或简称，然后点击联网搜索。除可选 LLM 摘要外，核心流程不需要 API key。",
            )
        )
        self.results_layout.addStretch()


class OnlineSearchResultCard(Card):
    def __init__(
        self,
        candidate: CompanySearchCandidate,
        *,
        on_add: Callable[[], None],
        on_source: Callable[[], None],
        on_detail: Callable[[], None],
    ) -> None:
        super().__init__("SuggestionItem")
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        market = QLabel(f"[{candidate.market or '公开来源'}]")
        market.setObjectName("StatusBadge")
        title = QLabel(candidate.name)
        title.setObjectName("CardTitle")
        title.setWordWrap(True)
        top.addWidget(market)
        top.addWidget(title, 1)
        score = QLabel(f"置信度 {int(round(candidate.confidence_score))}")
        score.setObjectName("ScorePill")
        top.addWidget(score)
        layout.addLayout(top)

        meta = QLabel(
            " · ".join(
                item
                for item in [
                    candidate.ticker,
                    candidate.exchange,
                    candidate.source_provider,
                    candidate.source_url.replace("https://", "").replace("http://", "").split("/")[0],
                ]
                if item
            )
        )
        meta.setObjectName("MutedText")
        meta.setWordWrap(True)
        layout.addWidget(meta)

        reason = QLabel(candidate.match_reason or "公开来源匹配")
        reason.setObjectName("MutedText")
        reason.setWordWrap(True)
        layout.addWidget(reason)
        if candidate.coverage_note:
            note = QLabel(candidate.coverage_note)
            note.setObjectName("EvidenceText")
            note.setWordWrap(True)
            layout.addWidget(note)

        actions = QHBoxLayout()
        detail_btn = QPushButton("查看详情")
        detail_btn.clicked.connect(on_detail)
        source_btn = QPushButton("查看来源")
        source_btn.clicked.connect(on_source)
        add_btn = QPushButton("已在自选" if candidate.already_watchlisted else "加入自选")
        add_btn.setEnabled(not candidate.already_watchlisted)
        add_btn.setObjectName("PrimaryButton")
        add_btn.clicked.connect(on_add)
        actions.addWidget(detail_btn)
        actions.addWidget(source_btn)
        actions.addWidget(add_btn)
        actions.addStretch()
        layout.addLayout(actions)
