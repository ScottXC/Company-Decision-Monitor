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


class AiSummaryPage(QWidget):
    route = "/ai-summary"
    page_title = "AI 总结 AI Summary"

    def __init__(self, navigate: Callable[[str], None]) -> None:
        super().__init__()
        self.navigate = navigate
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, layout = scroll_container()
        root.addWidget(scroll)
        layout.addWidget(
            PageHeader(
                "AI 总结",
                "未来用于对公司资料、公告证据和风险事件进行摘要。当前不调用任何 LLM 或外部服务。",
            )
        )
        layout.addWidget(PreviewNotice())
        layout.addWidget(
            EmptyState(
                "暂无 AI 总结",
                "接入 LLM 后可生成公司摘要和事件解读。AI 输出将被标注为仅供参考，并以原文证据为准。",
            )
        )
        layout.addWidget(
            PlaceholderTable(
                "AI 总结任务结构",
                ["公司", "摘要类型", "输入来源", "状态", "更新时间", "操作"],
                "当前版本不使用 API key，不上传本地数据，不生成 AI 内容。",
            )
        )
        layout.addStretch()
