from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from cdm_desktop.db import DatabaseManager
from cdm_desktop.db.models import Alert, Company, Document
from cdm_desktop.db.repositories import EventRepository, loads_json
from cdm_desktop.ui.widgets import (
    PriorityBadge,
    ScorePill,
    StatusBadge,
    format_score,
    priority_label,
)


class EventDetailDialog(QDialog):
    def __init__(self, db: DatabaseManager, event_id: int, parent: object | None = None) -> None:
        super().__init__(parent)
        self.db = db
        self.event_id = event_id
        self.source_url = ""
        self.setWindowTitle("事件详情")
        self.resize(920, 720)
        layout = QVBoxLayout(self)

        self.title_label = QLabel()
        self.title_label.setObjectName("DetailHeader")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.meta_row = QHBoxLayout()
        layout.addLayout(self.meta_row)

        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        layout.addWidget(self.summary, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.open_source_btn = QPushButton("打开来源 URL")
        self.open_source_btn.clicked.connect(self.open_source)
        buttons.addButton(self.open_source_btn, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()

    def refresh(self) -> None:
        with self.db.session() as session:
            event = EventRepository(session).get(self.event_id)
            company = session.get(Company, event.company_id)
            document = session.get(Document, event.document_id)
            alert = session.query(Alert).filter(Alert.event_id == event.id).order_by(Alert.created_at.desc()).first()
            evidence = EventRepository(session).evidence_for_event(event.id)
            components = loads_json(event.score_components_json, {}) or {}
            self.source_url = document.url if document else ""

            while self.meta_row.count():
                item = self.meta_row.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()

            priority = alert.priority if alert else "P3"
            self.title_label.setText(event.title)
            self.meta_row.addWidget(PriorityBadge(priority))
            self.meta_row.addWidget(StatusBadge(event.event_status))
            self.meta_row.addWidget(ScorePill("重大性", event.materiality_score))
            self.meta_row.addWidget(ScorePill("置信度", event.confidence_score))
            self.meta_row.addStretch()

            evidence_text = "\n\n".join(item.snippet for item in evidence) or "暂无证据片段"
            source_preview = (document.parsed_text or "")[:2500] if document else ""
            component_text = "\n".join(f"- {key}: {format_score(value)}" for key, value in components.items()) or "-"
            self.summary.setPlainText(
                "\n".join(
                    [
                        f"公司：{company.name if company else event.company_id}",
                        f"事件类型：{event.event_type}",
                        f"状态：{event.event_status}",
                        f"优先级：{priority_label(priority)}",
                        f"告警状态：{alert.status if alert else '未生成告警'}",
                        "",
                        "摘要：",
                        event.summary or "-",
                        "",
                        "置信度说明：",
                        event.confidence_explanation or "-",
                        "",
                        "重大性说明：",
                        event.materiality_explanation or "-",
                        "",
                        "评分组件：",
                        component_text,
                        "",
                        "证据片段：",
                        evidence_text,
                        "",
                        "来源文档预览：",
                        source_preview or "-",
                    ]
                )
            )
            self.open_source_btn.setEnabled(self.source_url.startswith(("http://", "https://")))

    def open_source(self) -> None:
        if self.source_url.startswith(("http://", "https://")):
            QDesktopServices.openUrl(QUrl(self.source_url))
