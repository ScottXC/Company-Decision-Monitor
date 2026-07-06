from __future__ import annotations

from cdm_desktop.paths import get_app_paths
from cdm_desktop.ui.main_window import MainWindow
from cdm_desktop.ui.pages import (
    AiSummaryPage,
    CompanyDetailPage,
    DashboardPage,
    HotCompaniesPage,
    RiskMonitorPage,
    SearchPage,
    SettingsPage,
    WatchlistPage,
)


def test_preview_window_routes_open(qtbot) -> None:
    window = MainWindow(get_app_paths())
    qtbot.addWidget(window)

    expected = [
        "首页",
        "公司搜索",
        "公司详情",
        "自选公司",
        "热门公司",
        "风险监控",
        "AI 总结",
        "设置",
    ]

    assert [window.sidebar.item(index).text() for index in range(window.sidebar.count())] == expected
    for index in range(window.sidebar.count()):
        window.sidebar.setCurrentRow(index)
        assert window.stack.currentIndex() == index


def test_preview_pages_can_be_constructed(qtbot) -> None:
    pages = [
        DashboardPage(lambda _route: None),
        SearchPage(lambda _route: None),
        CompanyDetailPage(lambda _route: None),
        WatchlistPage(lambda _route: None),
        HotCompaniesPage(lambda _route: None),
        RiskMonitorPage(lambda _route: None),
        AiSummaryPage(lambda _route: None),
        SettingsPage(lambda _route: None, get_app_paths()),
    ]

    for page in pages:
        qtbot.addWidget(page)
        assert page.page_title


def test_global_search_routes_to_search_page(qtbot) -> None:
    window = MainWindow(get_app_paths())
    qtbot.addWidget(window)

    window.global_search.setText("industry keyword")
    window.global_search.returnPressed.emit()

    assert window.state.current_route == "/search"
    assert window.state.search_keyword == "industry keyword"
