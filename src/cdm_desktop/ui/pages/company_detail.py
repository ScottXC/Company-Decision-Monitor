from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from cdm_desktop.ui.components import (
    EmptyState,
    MetricCard,
    PageHeader,
    PlaceholderChart,
    PlaceholderTable,
    PreviewNotice,
    SectionCard,
    metric_grid,
    scroll_container,
    show_preview_message,
)


class CompanyDetailPage(QWidget):
    route = "/company/placeholder"
    page_title = "公司详情 Company Detail"

    def __init__(self, navigate: Callable[[str], None]) -> None:
        super().__init__()
        self.navigate = navigate
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, layout = scroll_container()
        root.addWidget(scroll)

        layout.addWidget(
            PageHeader(
                "公司详情模板",
                "用于展示公司概览、财务摘要、新闻动态、重大事件、风险提示和 AI 总结的页面结构。",
                primary_text="添加自选",
                primary_action=lambda: show_preview_message(self, "添加自选"),
                secondary_text="返回搜索",
                secondary_action=lambda: self.navigate("/search"),
            )
        )
        layout.addWidget(PreviewNotice())

        header = SectionCard("公司头部信息区")
        header.layout.addWidget(
            EmptyState(
                "尚未选择公司",
                "公司名称、股票代码、行业、交易所、数据更新时间将在接入公司数据后显示。",
            )
        )
        action_row = QHBoxLayout()
        for text in ["添加自选", "移除自选", "设置提醒", "导出研究包"]:
            button = QPushButton(text)
            button.clicked.connect(lambda _checked=False, t=text: show_preview_message(self, t))
            action_row.addWidget(button)
        action_row.addStretch()
        header.layout.addLayout(action_row)
        layout.addWidget(header)

        layout.addWidget(
            metric_grid(
                [
                    MetricCard("收入", "—", "等待财务数据源"),
                    MetricCard("毛利率", "—", "等待财务数据源"),
                    MetricCard("净利润", "—", "等待财务数据源"),
                    MetricCard("市值", "—", "等待行情或财务数据"),
                    MetricCard("PE", "—", "等待估值数据"),
                    MetricCard("PS", "—", "等待估值数据"),
                    MetricCard("更新时间", "—", "等待数据同步"),
                    MetricCard("风险等级", "—", "等待风险规则"),
                ],
                columns=4,
            )
        )

        overview_grid = QGridLayout()
        overview = SectionCard("公司概览")
        overview.layout.addWidget(EmptyState("简介占位", "主营业务、所属行业和公司描述将在接入数据后显示。"))
        finance = PlaceholderChart("财务摘要占位", "未来展示收入、利润、现金流、利润率等趋势。")
        overview_grid.addWidget(overview, 0, 0)
        overview_grid.addWidget(finance, 0, 1)
        layout.addLayout(overview_grid)

        layout.addWidget(
            PlaceholderTable(
                "重大事件",
                ["时间", "事件类型", "状态", "风险等级", "证据", "操作"],
                "接入公告、新闻和事件规则后显示公司重大事件。",
            )
        )
        layout.addWidget(EmptyState("新闻动态", "接入新闻源后显示公司相关新闻。"))
        layout.addWidget(EmptyState("风险提示", "接入风险规则后显示潜在风险信号。"))
        layout.addWidget(EmptyState("AI 总结", "接入 LLM 后生成公司摘要和事件解读。"))
        layout.addStretch()
