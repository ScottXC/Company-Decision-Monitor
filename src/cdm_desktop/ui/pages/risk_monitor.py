from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QVBoxLayout, QWidget

from cdm_desktop.ui.components import (
    EmptyState,
    MetricCard,
    PageHeader,
    PlaceholderChart,
    PlaceholderTable,
    metric_grid,
    scroll_container,
)


class RiskMonitorPage(QWidget):
    route = "/risk-monitor"
    page_title = "风险监控 Risk Monitor"

    def __init__(self, navigate: Callable[[str], None]) -> None:
        super().__init__()
        self.navigate = navigate
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, layout = scroll_container()
        root.addWidget(scroll)
        layout.addWidget(
            PageHeader(
                "风险监控",
                "未来用于集中展示重大事件、监管风险、财务风险、舆情风险和供应链风险。",
            )
        )
        layout.addWidget(
            metric_grid(
                [
                    MetricCard("高风险", "0", "等待风险规则"),
                    MetricCard("中风险", "0", "等待风险规则"),
                    MetricCard("新增信号", "0", "等待数据源"),
                    MetricCard("待确认", "0", "等待人工复核流程"),
                ]
            )
        )
        layout.addWidget(EmptyState("暂无风险信号", "接入风险规则和公司动态数据后显示潜在风险信号。"))
        layout.addWidget(PlaceholderChart("风险趋势占位", "未来展示不同风险类型随时间变化。"))
        layout.addWidget(
            PlaceholderTable(
                "风险信号列表结构",
                ["公司", "风险类型", "等级", "触发依据", "证据", "更新时间", "操作"],
                "当前不执行真实风险检测，也不展示伪造风险事件。",
            )
        )
        layout.addStretch()
