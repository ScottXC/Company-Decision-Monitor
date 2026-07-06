from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QVBoxLayout, QWidget

from cdm_desktop.ui.components import (
    EmptyState,
    PageHeader,
    PlaceholderTable,
    PreviewNotice,
    scroll_container,
)


class HotCompaniesPage(QWidget):
    route = "/hot-companies"
    page_title = "热门公司 Hot Companies"

    def __init__(self, navigate: Callable[[str], None]) -> None:
        super().__init__()
        self.navigate = navigate
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, layout = scroll_container()
        root.addWidget(scroll)
        layout.addWidget(
            PageHeader(
                "热门公司",
                "展示公开信息热度较高公司的未来模块。当前不展示真实或伪造公司数据。",
                primary_text="搜索公司",
                primary_action=lambda: self.navigate("/search"),
            )
        )
        layout.addWidget(PreviewNotice())
        layout.addWidget(
            EmptyState(
                "暂无热门公司",
                "热门公司功能将在接入数据源后显示。该模块只表示公开信息热度，不构成投资建议。",
            )
        )
        layout.addWidget(
            PlaceholderTable(
                "热门公司列表结构",
                ["公司", "市场", "热度来源", "原因", "更新时间", "操作"],
                "未来可由公告数量、新闻提及、风险事件和最近搜索热度生成。",
            )
        )
        layout.addStretch()
