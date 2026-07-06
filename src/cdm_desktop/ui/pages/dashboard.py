from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from cdm_desktop.ui.components import (
    EmptyState,
    MetricCard,
    PageHeader,
    PlaceholderChart,
    PreviewNotice,
    SectionCard,
    StatusBadge,
    metric_grid,
    scroll_container,
)


class DashboardPage(QWidget):
    route = "/dashboard"
    page_title = "首页 Dashboard"

    def __init__(self, navigate: Callable[[str], None]) -> None:
        super().__init__()
        self.navigate = navigate
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, layout = scroll_container()
        root.addWidget(scroll)

        layout.addWidget(
            PageHeader(
                "公司决策监控",
                "搜索公司、添加自选、集中跟踪公司动态与风险信号。",
                primary_text="搜索公司",
                primary_action=lambda: self.navigate("/search"),
                secondary_text="查看自选",
                secondary_action=lambda: self.navigate("/watchlist"),
            )
        )
        layout.addWidget(PreviewNotice())
        layout.addWidget(
            metric_grid(
                [
                    MetricCard("自选公司", "0", "通过搜索添加关注后显示"),
                    MetricCard("风险信号", "0", "等待风险规则接入"),
                    MetricCard("公司动态", "0", "等待新闻与公告数据源"),
                    MetricCard("AI 总结", "未启用", "未来可接入 LLM"),
                ]
            )
        )

        hot = SectionCard("热门公司推荐", "热门公司功能将在接入数据源后显示。")
        hot.layout.addWidget(
            EmptyState(
                "暂无热门公司",
                "当前不展示真实公司或伪造公司数据。接入公开数据源后，这里会显示近期信息热度较高的公司。",
                action_text="查看热门公司模块",
                action=lambda: self.navigate("/hot-companies"),
            )
        )
        layout.addWidget(hot)

        grid = QGridLayout()
        watchlist = SectionCard("自选公司预览")
        watchlist.layout.addWidget(
            EmptyState(
                "暂无自选公司",
                "搜索公司后，可添加到自选列表集中跟踪。",
                action_text="打开公司搜索",
                action=lambda: self.navigate("/search"),
            )
        )
        recent = SectionCard("最近查看")
        recent.layout.addWidget(EmptyState("暂无最近查看", "打开公司详情后会在这里形成访问入口。"))
        grid.addWidget(watchlist, 0, 0)
        grid.addWidget(recent, 0, 1)
        layout.addLayout(grid)

        monitor = SectionCard("今日市场 / 舆情 / 公司动态")
        row = QHBoxLayout()
        for title, body, tone in [
            ("新闻", "等待新闻源接入", "neutral"),
            ("公告", "等待公告源接入", "neutral"),
            ("风险", "等待风险规则接入", "warning"),
            ("AI", "等待 LLM 设置", "info"),
        ]:
            card = SectionCard(title)
            card.layout.addWidget(StatusBadge(body, tone))
            row.addWidget(card)
        monitor.layout.addLayout(row)
        layout.addWidget(monitor)

        layout.addWidget(PlaceholderChart("信息流趋势占位", "未来用于展示公告、新闻、风险信号的时间分布。"))
        note = QLabel("本页面不包含真实公司、真实价格、投资建议或交易入口。")
        note.setObjectName("MutedText")
        layout.addWidget(note)
        layout.addStretch()
