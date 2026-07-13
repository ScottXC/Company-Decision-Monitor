from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QSize, QStringListModel, Qt, QThreadPool, QTimer
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop import PRODUCT_NAME_ZH
from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.models import CompanyResult
from cdm_desktop.store import PreviewUiState
from cdm_desktop.ui.pages import (
    CompanyDetailPage,
    DashboardPage,
    SearchPage,
    SettingsPage,
    WatchlistPage,
)
from cdm_desktop.ui.theme import ThemeManager
from cdm_desktop.ui.theme.tokens import CONTENT_MAX_WIDTH, NAV_WIDTH
from cdm_desktop.ui.widgets import FunctionWorker


class MainWindow(QMainWindow):
    def __init__(self, paths: AppPaths | None = None) -> None:
        super().__init__()
        self.paths = paths
        self.state = PreviewUiState()
        self._global_search_request_id = 0
        self._global_suggestions: dict[str, CompanyResult] = {}
        self._recent_searches: list[str] = []
        self._global_search_pool = QThreadPool(self)
        self._global_search_pool.setMaxThreadCount(2)
        self._global_search_timer = QTimer(self)
        self._global_search_timer.setSingleShot(True)
        self._global_search_timer.setInterval(350)
        self._global_search_timer.timeout.connect(self._start_global_suggestions)
        self.setWindowTitle(PRODUCT_NAME_ZH)
        self.resize(1440, 900)
        self.setMinimumSize(QSize(1100, 700))

        root = QWidget()
        root.setObjectName("AppRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_navigation())

        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)
        workspace_layout.addWidget(self._build_top_bar())

        content_host = QWidget()
        content_layout = QHBoxLayout(content_host)
        content_layout.setContentsMargins(28, 22, 28, 24)
        content_layout.setSpacing(0)
        self.stack = QStackedWidget()
        self.stack.setMaximumWidth(CONTENT_MAX_WIDTH)
        content_layout.addStretch()
        content_layout.addWidget(self.stack, 1)
        content_layout.addStretch()
        workspace_layout.addWidget(content_host, 1)
        root_layout.addWidget(workspace, 1)
        self.setCentralWidget(root)

        self.company_detail_page = CompanyDetailPage(self.navigate, paths)
        self.search_page = SearchPage(
            self.navigate,
            paths,
            on_company_selected=self._open_company_detail,
            on_watchlist_changed=self._refresh_watchlist,
        )
        self.watchlist_page = WatchlistPage(self.navigate, paths, on_company_selected=self._open_company_detail)
        self.dashboard_page = DashboardPage(self.navigate, paths)
        self.settings_page = SettingsPage(self.navigate, paths)

        self.pages: dict[str, QWidget] = {
            "/dashboard": self.dashboard_page,
            "/search": self.search_page,
            "/watchlist": self.watchlist_page,
            "/company/placeholder": self.company_detail_page,
            "/settings": self.settings_page,
        }
        self.route_index: dict[str, int] = {}
        for route, page in self.pages.items():
            self.route_index[route] = self.stack.addWidget(page)

        self.nav_routes = ["/dashboard", "/search", "/watchlist", "/settings"]
        self.sidebar.currentRowChanged.connect(self._show_nav_index)
        self.sidebar.setCurrentRow(0)

        self.search_shortcut = QShortcut(QKeySequence("Ctrl+K"), self, activated=self._focus_global_search)
        self.search_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._dismiss_global_search)
        self.escape_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)

    def _build_navigation(self) -> QWidget:
        shell = QWidget()
        shell.setObjectName("NavigationRail")
        shell.setFixedWidth(NAV_WIDTH)
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(16)

        brand = QHBoxLayout()
        mark = QLabel("CDM")
        mark.setObjectName("BrandMark")
        name = QLabel("Research")
        name.setObjectName("BrandName")
        brand.addWidget(mark)
        brand.addWidget(name)
        brand.addStretch()
        layout.addLayout(brand)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setIconSize(QSize(20, 20))
        navigation = [
            ("首页", QStyle.StandardPixmap.SP_ComputerIcon),
            ("搜索", QStyle.StandardPixmap.SP_FileDialogContentsView),
            ("自选", QStyle.StandardPixmap.SP_DialogYesButton),
            ("设置", QStyle.StandardPixmap.SP_FileDialogDetailedView),
        ]
        for label, icon in navigation:
            item = QListWidgetItem(self.style().standardIcon(icon), label)
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.sidebar.addItem(item)
        layout.addWidget(self.sidebar, 1)

        privacy = QLabel("本地优先 · 无交易功能")
        privacy.setObjectName("Caption")
        privacy.setWordWrap(True)
        layout.addWidget(privacy)
        return shell

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(72)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(28, 12, 24, 12)
        layout.setSpacing(12)

        self.global_search = QLineEdit()
        self.global_search.setObjectName("GlobalSearch")
        self.global_search.setPlaceholderText("搜索公司、股票代码或简称")
        self.global_search.setClearButtonEnabled(True)
        self.global_search.setMaximumWidth(620)
        self.global_search.returnPressed.connect(self._submit_global_search)
        self.global_search.textEdited.connect(self._queue_global_suggestions)
        self.global_search.installEventFilter(self)
        self.global_suggestion_model = QStringListModel(self)
        self.global_completer = QCompleter(self.global_suggestion_model, self)
        self.global_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.global_completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        self.global_completer.activated.connect(self._activate_global_suggestion)
        self.global_search.setCompleter(self.global_completer)
        layout.addWidget(self.global_search, 1)
        layout.addStretch()

        dot = QLabel("●")
        dot.setObjectName("ConnectionDot")
        dot.setToolTip("本地索引可用；公开数据按需补充")
        dot.setAccessibleName("数据连接状态：本地索引可用")
        layout.addWidget(dot)

        self.theme_button = QToolButton()
        self.theme_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarShadeButton))
        self.theme_button.setToolTip("切换浅色或深色主题")
        self.theme_button.setAccessibleName("切换主题")
        self.theme_button.setFixedSize(38, 38)
        self.theme_button.clicked.connect(self._toggle_theme)
        layout.addWidget(self.theme_button)

        settings = QToolButton()
        settings.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        settings.setToolTip("设置")
        settings.setAccessibleName("打开设置")
        settings.setFixedSize(38, 38)
        settings.clicked.connect(lambda: self.navigate("/settings"))
        layout.addWidget(settings)
        return bar

    def navigate(self, route: str) -> None:
        target = "/company/placeholder" if route.startswith("/company/") else route
        index = self.route_index.get(target, self.route_index["/dashboard"])
        self.stack.setCurrentIndex(index)
        self.state.current_route = target
        if target in self.nav_routes:
            nav_index = self.nav_routes.index(target)
            if self.sidebar.currentRow() != nav_index:
                self.sidebar.blockSignals(True)
                self.sidebar.setCurrentRow(nav_index)
                self.sidebar.blockSignals(False)
        else:
            self.sidebar.clearSelection()
        page = self.pages[target]
        refresh: Callable[[], None] | None = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()

    def _show_nav_index(self, index: int) -> None:
        if 0 <= index < len(self.nav_routes):
            self.navigate(self.nav_routes[index])

    def _submit_global_search(self) -> None:
        keyword = self.global_search.text().strip()
        if keyword and keyword not in self._recent_searches:
            self._recent_searches.insert(0, keyword)
            del self._recent_searches[8:]
        self.state.search_keyword = keyword
        self.navigate("/search")
        self.search_page.set_query(keyword)
        if keyword:
            self.search_page.run_search()

    def _focus_global_search(self) -> None:
        self.global_search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.global_search.selectAll()

    def _dismiss_global_search(self) -> None:
        self.global_completer.popup().hide()
        self.global_search.clearFocus()

    def _queue_global_suggestions(self, text: str) -> None:
        self._global_search_request_id += 1
        self._global_search_timer.stop()
        if not text.strip():
            self._show_recent_suggestions()
            return
        if len(text.strip()) >= 2:
            self._global_search_timer.start()

    def _start_global_suggestions(self) -> None:
        query = self.global_search.text().strip()
        if len(query) < 2:
            return
        request_id = self._global_search_request_id
        worker = FunctionWorker(self._run_global_suggestions, request_id, query)
        worker.signals.finished.connect(self._apply_global_suggestions)
        self._global_search_pool.start(worker)

    def _run_global_suggestions(self, request_id: int, query: str) -> tuple[int, str, list[CompanyResult]]:
        response = self.search_page.service.search_local(query, 6, use_cache=True)
        return request_id, query, response.companies[:6]

    def _apply_global_suggestions(self, payload: object) -> None:
        if not isinstance(payload, tuple) or len(payload) != 3:
            return
        request_id, query, companies = payload
        if request_id != self._global_search_request_id or query != self.global_search.text().strip():
            return
        self._global_suggestions = {}
        labels: list[str] = []
        for company in companies:
            identity = company.symbol or company.lei or company.company_number or "公开资料"
            market = company.exchange or company.market or company.country or ""
            label = f"{company.name or company.display_name}  ·  {identity}"
            if market:
                label += f"  ·  {market}"
            self._global_suggestions[label] = company
            labels.append(label)
        labels.append(f"查看所有结果：{query}")
        self.global_suggestion_model.setStringList(labels)
        self.global_completer.complete()

    def _activate_global_suggestion(self, text: str) -> None:
        company = self._global_suggestions.get(text)
        if company:
            self.global_search.setText(company.name or company.symbol)
            self._open_company_detail(company)
            return
        if text.startswith("查看所有结果："):
            self.global_search.setText(text.split("：", 1)[1])
        else:
            self.global_search.setText(text)
        self._submit_global_search()

    def _show_recent_suggestions(self) -> None:
        self._global_suggestions = {}
        self.global_suggestion_model.setStringList(self._recent_searches)
        if self._recent_searches:
            self.global_completer.complete()

    def eventFilter(self, watched: object, event: QEvent) -> bool:  # noqa: N802 - Qt override
        if watched is self.global_search and event.type() == QEvent.Type.FocusIn and not self.global_search.text():
            self._show_recent_suggestions()
        return super().eventFilter(watched, event)

    def _toggle_theme(self) -> None:
        manager = ThemeManager.instance()
        if manager:
            manager.toggle()

    def _open_company_detail(self, result: CompanyResult) -> None:
        self.company_detail_page.set_company(result)
        self.navigate("/company/placeholder")

    def _refresh_watchlist(self) -> None:
        self.watchlist_page.refresh()
        self.dashboard_page.refresh()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt override
        self._global_search_timer.stop()
        self._global_search_pool.clear()
        self.search_page.shutdown(wait_ms=250)
        self.company_detail_page.shutdown()
        super().closeEvent(event)
