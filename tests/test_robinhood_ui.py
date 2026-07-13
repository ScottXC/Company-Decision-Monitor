from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton, QScrollArea

from cdm_desktop.paths import AppPaths
from cdm_desktop.ui.main_window import MainWindow
from cdm_desktop.ui.pages import (
    CompanyDetailPage,
    DashboardPage,
    SearchPage,
    SettingsPage,
    WatchlistPage,
)
from cdm_desktop.ui.theme.theme_manager import ThemeManager


def make_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        raw_documents_dir=tmp_path / "raw_documents",
        exports_dir=tmp_path / "exports",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "cdm.db",
    ).ensure()


def test_light_and_dark_theme_resources_load(qapp) -> None:
    manager = ThemeManager(qapp)

    manager.apply("light", persist=False)
    assert qapp.property("cdmTheme") == "light"
    assert "#148a52" in qapp.styleSheet()
    manager.apply("dark", persist=False)
    assert qapp.property("cdmTheme") == "dark"
    assert "#35c979" in qapp.styleSheet()


def test_main_navigation_contains_only_primary_destinations(qtbot, tmp_path: Path) -> None:
    window = MainWindow(make_paths(tmp_path))
    qtbot.addWidget(window)

    assert [window.sidebar.item(index).text() for index in range(window.sidebar.count())] == ["首页", "搜索", "自选", "设置"]
    assert all("公司详情" not in window.sidebar.item(index).text() for index in range(window.sidebar.count()))


def test_ctrl_k_focuses_and_escape_dismisses_global_search(qtbot, tmp_path: Path) -> None:
    window = MainWindow(make_paths(tmp_path))
    qtbot.addWidget(window)
    window.show()
    window.activateWindow()
    qtbot.wait(20)

    qtbot.keyClick(window, Qt.Key.Key_K, modifier=Qt.KeyboardModifier.ControlModifier)
    assert window.global_search.hasFocus()
    qtbot.keyClick(window, Qt.Key.Key_Escape)
    assert not window.global_search.hasFocus()


def test_enter_submits_global_search(qtbot, tmp_path: Path, monkeypatch) -> None:
    window = MainWindow(make_paths(tmp_path))
    qtbot.addWidget(window)
    called: list[str] = []
    monkeypatch.setattr(window.search_page, "run_search", lambda: called.append(window.search_page.input.text()))

    window.global_search.setText("AAPL")
    window.global_search.returnPressed.emit()

    assert called == ["AAPL"]
    assert window.stack.currentWidget() is window.search_page


def test_global_search_suggestions_use_local_index_and_drop_stale_results(qtbot, tmp_path: Path) -> None:
    window = MainWindow(make_paths(tmp_path))
    qtbot.addWidget(window)
    window.global_search.setText("AAPL")
    window._global_search_request_id = 2
    stale = window._run_global_suggestions(1, "AAPL")
    window._apply_global_suggestions(stale)
    assert window.global_suggestion_model.stringList() == []

    current = window._run_global_suggestions(2, "AAPL")
    window._apply_global_suggestions(current)
    labels = window.global_suggestion_model.stringList()
    assert any("AAPL" in label and "Apple" in label for label in labels)
    assert labels[-1] == "查看所有结果：AAPL"


def test_primary_pages_construct_and_use_vertical_scroll(qtbot, tmp_path: Path) -> None:
    pages = [
        DashboardPage(lambda _route: None, make_paths(tmp_path / "dashboard")),
        SearchPage(lambda _route: None, make_paths(tmp_path / "search")),
        CompanyDetailPage(lambda _route: None, make_paths(tmp_path / "detail")),
        WatchlistPage(lambda _route: None, make_paths(tmp_path / "watchlist")),
        SettingsPage(lambda _route: None, make_paths(tmp_path / "settings")),
    ]
    for page in pages:
        qtbot.addWidget(page)
        scroll = page.findChild(QScrollArea)
        assert scroll is not None
        assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff


def test_ui_has_no_trading_actions_or_robinhood_brand(qtbot, tmp_path: Path) -> None:
    window = MainWindow(make_paths(tmp_path))
    qtbot.addWidget(window)
    button_text = " ".join(button.text() for button in window.findChildren(QPushButton))

    for forbidden in ("买入", "卖出", "下单", "持仓", "P&L", "目标价"):
        assert forbidden not in button_text
    assert "Robinhood" not in button_text


def test_1280_by_720_shell_has_no_primary_control_overlap(qtbot, tmp_path: Path) -> None:
    window = MainWindow(make_paths(tmp_path))
    qtbot.addWidget(window)
    window.resize(1280, 720)
    window.show()
    QApplication.processEvents()

    assert window.sidebar.parentWidget().width() == 196
    assert window.global_search.width() >= 300
    assert window.global_search.geometry().right() < window.theme_button.geometry().left()
    assert window.stack.geometry().width() > 700


def test_theme_files_are_in_pyinstaller_data_contract() -> None:
    source = (Path(__file__).parents[1] / "scripts" / "build_windows.py").read_text(encoding="utf-8")

    assert "cdm_desktop/ui/theme" in source
    assert '"light.qss"' in source
    assert '"dark.qss"' in source


def test_release_validator_requires_both_theme_resources() -> None:
    source = (Path(__file__).parents[1] / "scripts" / "validate_release_artifacts.py").read_text(encoding="utf-8")

    assert "cdm_desktop/ui/theme/light.qss" in source
    assert "cdm_desktop/ui/theme/dark.qss" in source
