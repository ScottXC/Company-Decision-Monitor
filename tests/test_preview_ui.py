from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QProgressBar, QTabWidget

from cdm_desktop.paths import AppPaths, get_app_paths
from cdm_desktop.public_api.key_store import ApiKeyStore
from cdm_desktop.public_api.models import ProviderMeta
from cdm_desktop.public_api.search_service import PublicSearchService
from cdm_desktop.ui.components import (
    MetricCard,
    friendly_state_label,
    metric_grid,
    sanitize_error_message,
    scroll_container,
)
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


def make_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        raw_documents_dir=tmp_path / "raw_documents",
        exports_dir=tmp_path / "exports",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "cdm.db",
    ).ensure()


def test_preview_window_routes_open(qtbot) -> None:
    window = MainWindow(get_app_paths())
    qtbot.addWidget(window)

    expected = ["工作台", "搜索公司", "自选清单", "公司档案", "数据源设置"]

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


def test_homepage_shows_public_network_mode(qtbot) -> None:
    window = MainWindow(get_app_paths())
    qtbot.addWidget(window)

    labels = [item.text() for item in window.findChildren(QLabel)]
    assert any("Public + Free API Network Mode" in text for text in labels)
    assert not any("UI Preview Mode" in text for text in labels)
    assert any("Company Decision Monitor" in text for text in labels)
    assert any("Company Decision Monitor" in text for text in labels)
    assert any("研究工作台" in text for text in labels)
    assert any("自选清单" in text for text in labels)
    assert not any("从这里开始" in text for text in labels)


def test_search_placeholder_explains_keyword_types(qtbot) -> None:
    page = SearchPage(lambda _route: None)
    qtbot.addWidget(page)

    placeholder = page.input.placeholderText()
    assert "公司" in placeholder
    assert "股票代码" in placeholder
    assert "简称" in placeholder
    assert "缩写" in placeholder


def test_search_region_prefilter_dropdown_exists(qtbot) -> None:
    page = SearchPage(lambda _route: None)
    qtbot.addWidget(page)

    combo = page.findChild(QComboBox)
    assert combo is not None
    labels = [combo.itemText(index) for index in range(combo.count())]
    assert "美国 / 美股" in labels
    combo.setCurrentIndex(labels.index("美国 / 美股"))
    assert page.current_region == "us"
    assert "美国证券目录" in page.region_hint.text()
    page_labels = [label.text() for label in page.findChildren(QLabel)]
    assert any("地区 / 国家" in text for text in page_labels)
    assert not any("搜索顺序" in text for text in page_labels)
    assert not any("1. 地区 / 国家初筛" in text for text in page_labels)


def test_watchlist_empty_state_exists(qtbot, tmp_path: Path) -> None:
    page = WatchlistPage(lambda _route: None, make_paths(tmp_path))
    qtbot.addWidget(page)

    labels = [label.text() for label in page.findChildren(QLabel)]
    assert any("暂无自选公司" in text for text in labels)
    assert any("自选筛选" in text for text in labels)
    assert any("自选公司" in text for text in labels)
    assert not any("自选使用流程" in text for text in labels)


def test_settings_has_grouped_api_key_entry_and_masks_existing_key(qtbot, tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    ApiKeyStore(paths).set("FMP_API_KEY", "abcd1234efgh5678")
    page = SettingsPage(lambda _route: None, paths)
    qtbot.addWidget(page)

    tabs = page.findChild(QTabWidget)
    assert tabs is not None
    assert "免费 API key" in [tabs.tabText(index) for index in range(tabs.count())]
    placeholders = [edit.placeholderText() for edit in page.findChildren(QLineEdit)]
    assert any("abcd...5678" in text for text in placeholders)
    assert all("abcd1234efgh5678" not in text for text in placeholders)
    labels = [label.text() for label in page.findChildren(QLabel)]
    assert not any("设置顺序" in text for text in labels)


def test_provider_state_and_error_text_are_user_friendly() -> None:
    assert friendly_state_label("not_configured") == "未配置"
    assert "Traceback" not in sanitize_error_message("Traceback JSONDecodeError Exception")


def test_scroll_container_prevents_horizontal_overflow() -> None:
    scroll, _content, _layout = scroll_container()

    assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff


def test_metric_grid_caps_columns_to_avoid_card_overlap(qtbot) -> None:
    grid = metric_grid(
        [
            MetricCard("A", "1", "x"),
            MetricCard("B", "2", "x"),
            MetricCard("C", "3", "x"),
            MetricCard("D", "4", "x"),
        ],
        columns=4,
    )
    qtbot.addWidget(grid)
    layout = grid.layout()

    assert layout.itemAtPosition(0, 0) is not None
    assert layout.itemAtPosition(0, 1) is not None
    assert layout.itemAtPosition(0, 2) is None
    assert layout.itemAtPosition(1, 0) is not None


def test_settings_connection_progress_bar_updates(qtbot, tmp_path: Path) -> None:
    page = SettingsPage(lambda _route: None, make_paths(tmp_path))
    qtbot.addWidget(page)

    progress = page.findChild(QProgressBar)
    assert progress is not None

    page.test_panel.setVisible(True)
    page._update_test_progress(1, 3, "正在测试公开数据源")

    assert progress.maximum() == 3
    assert progress.value() == 1
    assert "正在测试公开数据源" in page.test_status_label.text()


def test_provider_connectivity_reports_progress_without_network(tmp_path: Path) -> None:
    service = PublicSearchService(make_paths(tmp_path))
    service.registry.providers = [
        ProviderMeta(
            "stub",
            "Stub Provider",
            "fallback",
            "test",
            "test",
            False,
            None,
            "none",
            "https://example.invalid",
            False,
        ),
        ProviderMeta(
            "needs_key",
            "Needs Key Provider",
            "news",
            "test",
            "test",
            True,
            "MISSING_TEST_KEY",
            "none",
            "https://example.invalid",
            True,
        ),
    ]
    progress: list[tuple[int, int, str]] = []

    statuses = service.test_provider_connectivity(
        progress_callback=lambda current, total, message: progress.append((current, total, message))
    )

    assert [status.state for status in statuses] == ["disabled", "not_configured"]
    assert progress[0][0] == 0
    assert progress[-1][0] == progress[-1][1] == 2
