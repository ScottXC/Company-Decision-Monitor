from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTableWidget, QTextEdit, QVBoxLayout, QWidget

from cdm_desktop.event_engine.taxonomy import EVENT_DEFINITIONS
from cdm_desktop.ui.widgets import set_table_rows


class LearnPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel("学习")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        note = QTextEdit()
        note.setReadOnly(True)
        note.setMaximumHeight(140)
        note.setPlainText(
            "这里整理本工具会识别的重大决策类型、默认重大性权重和关键词方向。"
            "这些内容用于资料整理和人工复核，不构成投资建议，也不会触发任何交易动作。"
        )
        layout.addWidget(note)

        self.table = QTableWidget()
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        definitions = list(EVENT_DEFINITIONS.values())
        set_table_rows(
            self.table,
            ["事件类型", "中文名称", "默认权重", "中文关键词", "英文关键词"],
            [
                [
                    item.event_type,
                    item.display_name_zh,
                    item.materiality_weight,
                    " / ".join(item.keywords_zh[:5]),
                    " / ".join(item.keywords_en[:5]),
                ]
                for item in definitions
            ],
            list(range(1, len(definitions) + 1)),
        )
