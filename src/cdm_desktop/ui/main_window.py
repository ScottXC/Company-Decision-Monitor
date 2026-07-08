from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop import APP_MODE_LABEL, PRODUCT_NAME_ZH
from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.models import CompanyResult
from cdm_desktop.store import PreviewUiState
from cdm_desktop.ui.components import StatusBadge, show_preview_message
from cdm_desktop.ui.pages import (
    CompanyDetailPage,
    DashboardPage,
    SearchPage,
    SettingsPage,
    WatchlistPage,
)


class MainWindow(QMainWindow):
    def __init__(self, paths: AppPaths | None = None) -> None:
        super().__init__()
        self.paths = paths
        self.state = PreviewUiState()
        self.setWindowTitle(PRODUCT_NAME_ZH)
        self.resize(1360, 820)
        self.setMinimumSize(QSize(1180, 720))

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar_shell = QWidget()
        sidebar_shell.setObjectName("SidebarShell")
        sidebar_shell.setFixedWidth(228)
        sidebar_layout = QVBoxLayout(sidebar_shell)
        sidebar_layout.setContentsMargins(18, 18, 18, 18)
        sidebar_layout.setSpacing(10)
        product = QLabel("CDM Research")
        product.setObjectName("SidebarTitle")
        product.setWordWrap(True)
        sidebar_layout.addWidget(product)
        subtitle = QLabel("Company Decision Monitor")
        subtitle.setObjectName("SidebarSubtitle")
        sidebar_layout.addWidget(subtitle)
        sidebar_layout.addWidget(StatusBadge(APP_MODE_LABEL, "info"))

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("Sidebar")
        sidebar_layout.addWidget(self.sidebar, 1)
        root_layout.addWidget(sidebar_shell)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 16, 22, 18)
        content_layout.setSpacing(12)
        root_layout.addWidget(content, 1)

        header = QHBoxLayout()
        header.setSpacing(12)
        self.page_title = QLabel("工作台")
        self.page_title.setObjectName("PageTitle")
        header.addWidget(self.page_title)
        header.addWidget(StatusBadge("公开数据源", "success"))
        header.addWidget(StatusBadge(APP_MODE_LABEL, "info"))
        header.addStretch()
        self.global_search = QLineEdit()
        self.global_search.setPlaceholderText("搜索公司、股票代码、简称、缩写、LEI 或注册号...")
        self.global_search.setMinimumWidth(260)
        self.global_search.setMaximumWidth(460)
        self.global_search.returnPressed.connect(self._submit_global_search)
        header.addWidget(self.global_search, 1)
        settings_btn = QPushButton("设置")
        settings_btn.clicked.connect(lambda: self.navigate("/settings"))
        header.addWidget(settings_btn)
        content_layout.addLayout(header)

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.company_detail_page = CompanyDetailPage(self.navigate, paths)
        self.search_page = SearchPage(
            self.navigate,
            paths,
            on_company_selected=self._open_company_detail,
            on_watchlist_changed=self._refresh_watchlist,
        )
        self.watchlist_page = WatchlistPage(
            self.navigate,
            paths,
            on_company_selected=self._open_company_detail,
        )
        self.dashboard_page = DashboardPage(self.navigate, paths)
        self.settings_page = SettingsPage(self.navigate, paths)

        self.routes: list[tuple[str, str, QWidget]] = [
            ("/dashboard", "工作台", self.dashboard_page),
            ("/search", "搜索公司", self.search_page),
            ("/watchlist", "自选清单", self.watchlist_page),
            ("/company/placeholder", "公司档案", self.company_detail_page),
            ("/settings", "数据源设置", self.settings_page),
        ]
        self.route_index = {route: index for index, (route, _label, _page) in enumerate(self.routes)}
        for _route, label, page in self.routes:
            item = QListWidgetItem(label)
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.sidebar.addItem(item)
            self.stack.addWidget(page)
        self.sidebar.currentRowChanged.connect(self._show_index)
        self.sidebar.setCurrentRow(0)

    def navigate(self, route: str) -> None:
        index = self.route_index.get(route)
        if index is None:
            index = self.route_index["/company/placeholder"] if route.startswith("/company/") else 0
        self.sidebar.setCurrentRow(index)

    def _show_index(self, index: int) -> None:
        if index < 0:
            return
        self.stack.setCurrentIndex(index)
        route, label, page = self.routes[index]
        self.state.current_route = route
        self.page_title.setText(getattr(page, "page_title", label))
        refresh: Callable[[], None] | None = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()

    def _submit_global_search(self) -> None:
        keyword = self.global_search.text().strip()
        self.state.search_keyword = keyword
        self.navigate("/search")
        self.search_page.set_query(keyword)
        if keyword:
            self.search_page.run_search()
        else:
            show_preview_message(self, "全局搜索")

    def _open_company_detail(self, result: CompanyResult) -> None:
        self.company_detail_page.set_company(result)
        self.navigate("/company/placeholder")

    def _refresh_watchlist(self) -> None:
        self.watchlist_page.refresh()
        self.dashboard_page.refresh()
