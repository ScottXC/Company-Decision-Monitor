from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop.db import DatabaseManager
from cdm_desktop.db.repositories import DocumentRepository
from cdm_desktop.paths import AppPaths
from cdm_desktop.services.event_service import EventService
from cdm_desktop.services.parsing_service import ParsingService
from cdm_desktop.ui.widgets import TextViewerDialog, info, selected_id, set_table_rows, warn


class DocumentsPage(QWidget):
    def __init__(self, db: DatabaseManager, paths: AppPaths) -> None:
        super().__init__()
        self.db = db
        self.paths = paths
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索文档")
        self.search.textChanged.connect(self.refresh)
        for text, slot in [
            ("查看全文", self.view_text),
            ("打开来源URL", self.open_url),
            ("重新解析", self.reparse),
            ("提取事件", self.extract_events),
        ]:
            button = QPushButton(text)
            button.clicked.connect(slot)
            top.addWidget(button)
        top.insertWidget(0, self.search, 1)
        layout.addLayout(top)
        self.table = QTableWidget()
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        with self.db.session() as session:
            docs = DocumentRepository(session).list(self.search.text())
            set_table_rows(
                self.table,
                ["ID", "标题", "URL", "类型", "解析状态", "抓取时间"],
                [[d.id, d.title or "", d.url, d.content_type or "", d.parse_status, d.fetched_at.strftime("%Y-%m-%d %H:%M")] for d in docs],
                [d.id for d in docs],
            )

    def _current_document(self):
        document_id = selected_id(self.table)
        if document_id is None:
            warn(self, "请先选择文档")
            return None
        with self.db.session() as session:
            doc = DocumentRepository(session).get(document_id)
            return {
                "id": doc.id,
                "title": doc.title or "",
                "text": doc.parsed_text or "",
                "url": doc.url,
                "raw_path": doc.raw_content_path,
                "content_type": doc.content_type,
            }

    def view_text(self) -> None:
        doc = self._current_document()
        if not doc:
            return
        TextViewerDialog(str(doc["title"]), str(doc["text"]), self).exec()

    def open_url(self) -> None:
        doc = self._current_document()
        if not doc:
            return
        if not str(doc["url"]).startswith(("http://", "https://")):
            warn(self, "该文档没有可打开的外部 HTTP/HTTPS 来源 URL")
            return
        QDesktopServices.openUrl(QUrl(str(doc["url"])))

    def reparse(self) -> None:
        doc_info = self._current_document()
        if not doc_info:
            return
        raw_path = doc_info["raw_path"]
        if not raw_path or not Path(str(raw_path)).exists():
            warn(self, "找不到原始文档文件")
            return
        parsed = ParsingService().parse(Path(str(raw_path)).read_bytes(), str(doc_info["content_type"]), str(doc_info["title"]))
        with self.db.session() as session:
            doc = DocumentRepository(session).get(int(doc_info["id"]))
            doc.parsed_text = parsed.parsed_text
            doc.parse_status = parsed.parse_status
            doc.parse_error = parsed.parse_error
            doc.metadata_json = parsed.metadata_json
        self.refresh()
        info(self, "重新解析完成")

    def extract_events(self) -> None:
        doc = self._current_document()
        if not doc:
            return
        with self.db.session() as session:
            count = len(EventService().process_document(session, int(doc["id"])))
        info(self, f"事件提取完成，新增 {count} 条")
