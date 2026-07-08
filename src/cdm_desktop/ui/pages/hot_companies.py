from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QVBoxLayout, QWidget

from cdm_desktop.ui.components import EmptyState, PageHeader, PreviewNotice, scroll_container


class HotCompaniesPage(QWidget):
    route = "/hot-companies"
    page_title = "热门公司 Hot Companies"

    def __init__(self, navigate: Callable[[str], None]) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, layout = scroll_container()
        root.addWidget(scroll)
        layout.addWidget(
            PageHeader(
                "热门公司",
                "热门公司需要可靠公开来源。当前版本不会展示伪造热度或假公司列表。",
                primary_text="搜索公司",
                primary_action=lambda: navigate("/search"),
            )
        )
        layout.addWidget(PreviewNotice())
        layout.addWidget(
            EmptyState(
                "热门公司暂未接入可靠来源",
                "后续版本会基于真实新闻 provider、搜索热度和公开事件频次生成，不构成投资建议。",
            )
        )
        layout.addStretch()
