from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop.ui.components import (
    EmptyState,
    LoadingState,
    PageHeader,
    PlaceholderTable,
    SectionCard,
    scroll_container,
    show_preview_message,
)

SCOPES = [
    ("全部", "all"),
    ("A 股", "a_share"),
    ("港股", "hk"),
    ("美股", "us"),
    ("未上市公司", "private"),
    ("行业关键词", "industry"),
]


class SearchPage(QWidget):
    route = "/search"
    page_title = "公司搜索 Search"

    def __init__(self, navigate: Callable[[str], None]) -> None:
        super().__init__()
        self.navigate = navigate
        self.current_scope = "all"
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, layout = scroll_container()
        root.addWidget(scroll)

        layout.addWidget(
            PageHeader(
                "公司搜索",
                "LinkedIn 式关键词搜索体验占位。当前不执行真实联网搜索，也不返回伪造公司数据。",
            )
        )

        search_card = SectionCard("搜索公司", "输入公司名称、股票代码、简称、品牌或行业关键词。")
        search_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("搜索公司名称、股票代码、简称...")
        self.input.returnPressed.connect(self.run_search)
        search_btn = QPushButton("搜索")
        search_btn.setObjectName("PrimaryButton")
        search_btn.clicked.connect(self.run_search)
        search_row.addWidget(self.input, 1)
        search_row.addWidget(search_btn)
        search_card.layout.addLayout(search_row)

        scope_row = QHBoxLayout()
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
        search_card.layout.addLayout(scope_row)
        layout.addWidget(search_card)

        self.result_host = QVBoxLayout()
        layout.addLayout(self.result_host)
        self._show_initial_state()
        layout.addStretch()

    def set_query(self, keyword: str) -> None:
        self.input.setText(keyword)
        self.input.setFocus()

    def run_search(self) -> None:
        self._clear_results()
        keyword = self.input.text().strip()
        if not keyword:
            self._show_initial_state()
            return
        self.result_host.addWidget(LoadingState("正在展示搜索加载状态占位..."))
        QTimer.singleShot(450, lambda: self._show_preview_result(keyword))

    def _scope_changed(self) -> None:
        button = self.sender()
        if isinstance(button, QPushButton):
            self.current_scope = str(button.property("scope"))

    def _show_initial_state(self) -> None:
        self.result_host.addWidget(
            EmptyState(
                "开始搜索公司",
                "输入关键词后会展示搜索状态。当前版本仅保留 UI 和未来数据接口，不接真实搜索源。",
            )
        )
        self.result_host.addWidget(
            PlaceholderTable(
                "搜索结果结构占位",
                ["公司名称", "股票代码", "交易所", "行业", "简介", "操作"],
                "搜索结果卡片将在接入数据源后展示；当前不显示伪造公司。",
            )
        )

    def _show_preview_result(self, keyword: str) -> None:
        self._clear_results()
        self.result_host.addWidget(
            EmptyState(
                "暂无搜索结果",
                f"已输入：{keyword}。当前为 UI Preview Mode，尚未接入公司搜索数据源。",
                action_text="查看公司详情模板",
                action=lambda: self.navigate("/company/placeholder"),
            )
        )
        actions = SectionCard("结果卡片未来结构")
        actions.layout.addWidget(QLabel("公司名称位置 · 股票代码位置 · 交易所位置 · 行业位置 · 简介位置"))
        row = QHBoxLayout()
        for text in ["添加自选", "查看详情", "筛选范围"]:
            button = QPushButton(text)
            button.clicked.connect(lambda _checked=False, t=text: show_preview_message(self, t))
            row.addWidget(button)
        row.addStretch()
        actions.layout.addLayout(row)
        self.result_host.addWidget(actions)

    def _clear_results(self) -> None:
        while self.result_host.count():
            item = self.result_host.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
