from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QVBoxLayout, QWidget

from cdm_desktop.ui.components import EmptyState, PageHeader, PreviewNotice, scroll_container


class RiskMonitorPage(QWidget):
    route = "/risk-monitor"
    page_title = "风险监控 Risk Monitor"

    def __init__(self, navigate: Callable[[str], None]) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, layout = scroll_container()
        root.addWidget(scroll)
        layout.addWidget(
            PageHeader(
                "风险监控",
                "风险规则引擎暂未接入。当前页面仅说明后续会基于真实公告、新闻和注册数据生成风险信号。",
                primary_text="返回首页",
                primary_action=lambda: navigate("/dashboard"),
            )
        )
        layout.addWidget(PreviewNotice())
        layout.addWidget(
            EmptyState(
                "风险规则引擎暂未接入",
                "不会显示假风险等级。后续接入时将展示 provider、证据、更新时间和规则解释。",
            )
        )
        layout.addStretch()
