from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from cdm_desktop.ui.components import (
    EmptyState,
    PageHeader,
    PlaceholderTable,
    SectionCard,
    scroll_container,
    show_preview_message,
)


class WatchlistPage(QWidget):
    route = "/watchlist"
    page_title = "自选公司 Watchlist"

    def __init__(self, navigate: Callable[[str], None]) -> None:
        super().__init__()
        self.navigate = navigate
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, layout = scroll_container()
        root.addWidget(scroll)

        layout.addWidget(
            PageHeader(
                "自选公司",
                "集中管理关注公司。当前版本不读取历史用户数据，列表保持空状态。",
                primary_text="搜索添加",
                primary_action=lambda: self.navigate("/search"),
                secondary_text="批量管理",
                secondary_action=lambda: show_preview_message(self, "批量管理"),
            )
        )

        tools = SectionCard("列表工具")
        row = QHBoxLayout()
        for label in ["全部分组", "按市场筛选", "按风险排序"]:
            combo = QComboBox()
            combo.addItem(label)
            combo.setToolTip("UI 占位：接入自选公司数据后可用")
            row.addWidget(combo)
        for text in ["新建分组", "导入列表", "删除所选"]:
            button = QPushButton(text)
            button.clicked.connect(lambda _checked=False, t=text: show_preview_message(self, t))
            row.addWidget(button)
        row.addStretch()
        tools.layout.addLayout(row)
        layout.addWidget(tools)

        layout.addWidget(
            EmptyState(
                "暂无自选公司",
                "通过公司搜索添加关注后，可在这里集中查看公司动态。",
                action_text="打开公司搜索",
                action=lambda: self.navigate("/search"),
            )
        )
        layout.addWidget(
            PlaceholderTable(
                "自选公司列表结构",
                ["公司", "市场", "行业", "最新动态", "风险等级", "更新时间", "操作"],
                "删除、快速进入详情、分组、筛选、排序均为 UI 占位，等待自选公司数据接入。",
            )
        )
        layout.addStretch()
