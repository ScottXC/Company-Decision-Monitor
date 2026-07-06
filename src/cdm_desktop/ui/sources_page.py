from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop.db import DatabaseManager
from cdm_desktop.db.repositories import SourceRepository
from cdm_desktop.paths import AppPaths
from cdm_desktop.services.ingestion_service import IngestionService
from cdm_desktop.ui.widgets import FunctionWorker, info, selected_id, set_table_rows, warn


class SourcesPage(QWidget):
    def __init__(self, db: DatabaseManager, paths: AppPaths, refresh_callback: Callable[[], None]) -> None:
        super().__init__()
        self.db = db
        self.paths = paths
        self.refresh_callback = refresh_callback
        self.ingestion = IngestionService(db, paths)
        self.thread_pool = QThreadPool.globalInstance()
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        for text, slot in [
            ("添加数据源", self.add_source),
            ("编辑", self.edit_source),
            ("删除", self.delete_source),
            ("启用/停用", self.toggle_source),
            ("运行选中", self.run_selected),
            ("运行全部启用源", self.run_all),
        ]:
            button = QPushButton(text)
            if text == "添加数据源":
                button.setObjectName("PrimaryButton")
            button.clicked.connect(slot)
            top.addWidget(button)
        top.addStretch()
        layout.addLayout(top)
        self.table = QTableWidget()
        self.runs_table = QTableWidget()
        layout.addWidget(self.table)
        layout.addWidget(self.runs_table)
        self.refresh()

    def refresh(self) -> None:
        with self.db.session() as session:
            sources = SourceRepository(session).list()
            set_table_rows(
                self.table,
                ["ID", "名称", "类型", "URL", "启用", "最近运行"],
                [
                    [
                        s.id,
                        s.name,
                        s.source_type,
                        s.url,
                        "是" if s.enabled else "否",
                        s.last_run_at.strftime("%Y-%m-%d %H:%M") if s.last_run_at else "",
                    ]
                    for s in sources
                ],
                [s.id for s in sources],
            )
            runs = SourceRepository(session).latest_runs(50)
            set_table_rows(
                self.runs_table,
                ["ID", "源ID", "状态", "发现", "新增", "错误", "开始", "结束"],
                [
                    [
                        r.id,
                        r.source_id,
                        r.status,
                        r.documents_found,
                        r.documents_created,
                        r.error_message or "",
                        r.started_at.strftime("%Y-%m-%d %H:%M:%S"),
                        r.finished_at.strftime("%Y-%m-%d %H:%M:%S") if r.finished_at else "",
                    ]
                    for r in runs
                ],
                [r.id for r in runs],
            )

    def add_source(self) -> None:
        dialog = SourceDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        with self.db.session() as session:
            SourceRepository(session).create(**dialog.values())
        self.refresh()

    def edit_source(self) -> None:
        source_id = selected_id(self.table)
        if source_id is None:
            warn(self, "请先选择数据源")
            return
        with self.db.session() as session:
            source = SourceRepository(session).get(source_id)
            values = {
                "name": source.name,
                "source_type": source.source_type,
                "url": source.url,
                "enabled": source.enabled,
            }
        dialog = SourceDialog(self, values)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        with self.db.session() as session:
            SourceRepository(session).update(source_id, **dialog.values())
        self.refresh()

    def delete_source(self) -> None:
        source_id = selected_id(self.table)
        if source_id is None:
            warn(self, "请先选择数据源")
            return
        answer = QMessageBox.question(self, "删除数据源", "确定删除选中的数据源吗？")
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            with self.db.session() as session:
                source = SourceRepository(session).get(source_id)
                session.delete(source)
        except Exception as exc:
            warn(self, f"删除数据源失败：{exc}")
            return
        self.refresh()

    def toggle_source(self) -> None:
        source_id = selected_id(self.table)
        if source_id is None:
            warn(self, "请先选择数据源")
            return
        with self.db.session() as session:
            repo = SourceRepository(session)
            source = repo.get(source_id)
            repo.update(source_id, enabled=not source.enabled)
        self.refresh()

    def run_selected(self) -> None:
        source_id = selected_id(self.table)
        if source_id is None:
            warn(self, "请先选择数据源")
            return
        self._run_worker(self.ingestion.run_source, source_id)

    def run_all(self) -> None:
        self._run_worker(self.ingestion.run_all_enabled_sources)

    def _run_worker(self, func: object, *args: object) -> None:
        worker = FunctionWorker(func, *args)
        worker.signals.finished.connect(self._worker_finished)
        worker.signals.error.connect(lambda message: warn(self, f"采集失败：\n{message}"))
        self.thread_pool.start(worker)

    def _worker_finished(self, result: object) -> None:
        self.refresh()
        self.refresh_callback()
        info(self, f"采集完成：{result}")


class SourceDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, values: dict[str, object] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("数据源")
        values = values or {}
        layout = QFormLayout(self)
        self.name = QLineEdit(str(values.get("name", "")))
        self.source_type = QComboBox()
        self.source_type.addItems(["manual_url", "rss", "webpage", "sec_edgar"])
        current_type = str(values.get("source_type", "manual_url"))
        index = self.source_type.findText(current_type)
        self.source_type.setCurrentIndex(max(0, index))
        self.url = QLineEdit(str(values.get("url", "")))
        self.enabled = QCheckBox()
        self.enabled.setChecked(bool(values.get("enabled", True)))
        layout.addRow("名称", self.name)
        layout.addRow("类型", self.source_type)
        layout.addRow("URL", self.url)
        layout.addRow("启用", self.enabled)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> dict[str, object]:
        return {
            "name": self.name.text().strip() or "未命名数据源",
            "source_type": self.source_type.currentText(),
            "url": self.url.text().strip(),
            "enabled": self.enabled.isChecked(),
            "config": {},
        }
