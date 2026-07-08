from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QVBoxLayout, QWidget

from cdm_desktop.ui.components import EmptyState, PageHeader, PreviewNotice, scroll_container


class AiSummaryPage(QWidget):
    route = "/ai-summary"
    page_title = "AI 总结 AI Summary"

    def __init__(self, navigate: Callable[[str], None]) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, layout = scroll_container()
        root.addWidget(scroll)
        layout.addWidget(
            PageHeader(
                "AI 总结",
                "AI 总结暂未接入。未来只用于总结真实 provider 返回的证据，不参与事实识别或投资建议。",
                primary_text="返回首页",
                primary_action=lambda: navigate("/dashboard"),
            )
        )
        layout.addWidget(PreviewNotice())
        layout.addWidget(
            EmptyState(
                "AI 总结暂未接入",
                "当前不会调用任何 LLM，也不会保存 AI key。后续接入时会明确标注“AI 摘要，仅供参考”。",
            )
        )
        layout.addStretch()
