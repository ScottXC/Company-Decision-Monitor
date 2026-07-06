from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop.db import DatabaseManager
from cdm_desktop.db.repositories import CompanyRepository, DocumentRepository, EventRepository
from cdm_desktop.paths import AppPaths
from cdm_desktop.ui.company_detail_dialog import CompanyDetailDialog
from cdm_desktop.ui.widgets import selected_id, set_table_rows, warn


class ResearchPage(QWidget):
    def __init__(self, db: DatabaseManager, paths: AppPaths) -> None:
        super().__init__()
        self.db = db
        self.paths = paths

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel("发现")
        title.setObjectName("PageTitle")
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索公司、代码、别名、事件或资讯")
        self.search.textChanged.connect(self.refresh)
        detail_btn = QPushButton("打开公司详情")
        detail_btn.clicked.connect(self.open_company_detail)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.search, 1)
        header.addWidget(detail_btn)
        layout.addLayout(header)

        layout.addWidget(QLabel("观察列表"))
        self.company_table = QTableWidget()
        layout.addWidget(self.company_table, 2)

        layout.addWidget(QLabel("重大事件"))
        self.event_table = QTableWidget()
        layout.addWidget(self.event_table, 2)

        layout.addWidget(QLabel("资讯流"))
        self.document_table = QTableWidget()
        layout.addWidget(self.document_table, 2)
        self.refresh()

    def refresh(self) -> None:
        query = self.search.text().strip()
        with self.db.session() as session:
            companies = CompanyRepository(session).list(query, "all")
            events = EventRepository(session).list(limit=100)
            documents = DocumentRepository(session).list(query, limit=100)
            if query:
                lowered = query.lower()
                events = [
                    event
                    for event in events
                    if lowered in event.title.lower()
                    or lowered in event.event_type.lower()
                    or lowered in event.event_status.lower()
                    or lowered in (event.summary or "").lower()
                ]

            set_table_rows(
                self.company_table,
                ["ID", "名称", "代码", "行业", "国家/地区", "别名数"],
                [[c.id, c.name, c.ticker or "", c.industry or "", c.country or "", len(c.aliases)] for c in companies],
                [c.id for c in companies],
            )
            set_table_rows(
                self.event_table,
                ["ID", "公司ID", "类型", "状态", "标题", "重大性", "置信度"],
                [
                    [
                        e.id,
                        e.company_id,
                        e.event_type,
                        e.event_status,
                        e.title,
                        e.materiality_score,
                        e.confidence_score,
                    ]
                    for e in events
                ],
                [e.id for e in events],
            )
            set_table_rows(
                self.document_table,
                ["ID", "标题", "类型", "解析状态", "抓取时间"],
                [
                    [
                        d.id,
                        d.title or "",
                        d.content_type or "",
                        d.parse_status,
                        d.fetched_at.strftime("%Y-%m-%d %H:%M"),
                    ]
                    for d in documents
                ],
                [d.id for d in documents],
            )

    def open_company_detail(self) -> None:
        company_id = selected_id(self.company_table)
        if company_id is None:
            warn(self, "请先选择公司")
            return
        CompanyDetailDialog(self.db, company_id, self).exec()
