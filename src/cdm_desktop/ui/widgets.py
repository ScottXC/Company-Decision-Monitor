from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop.db import DatabaseManager
from cdm_desktop.services.hot_company_service import HotCompanyCandidate

PRIORITY_LABELS = {
    "P0": "严重",
    "P1": "高",
    "P2": "中",
    "P3": "低",
}

STATUS_LABELS = {
    "rumored": "传闻",
    "proposed": "拟议",
    "board_approved": "董事会通过",
    "shareholder_approved": "股东大会通过",
    "announced": "已公告",
    "completed": "已完成",
    "terminated": "已终止",
    "denied": "已否认",
    "unknown": "未知",
}

ALERT_STATUS_LABELS = {
    "unread": "未读",
    "acknowledged": "已读",
    "ignored": "已忽略",
}

class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)


class FunctionWorker(QRunnable):
    def __init__(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.finished.emit(self.func(*self.args, **self.kwargs))
        except Exception:
            self.signals.error.emit(traceback.format_exc())


def priority_label(priority: str | None) -> str:
    return PRIORITY_LABELS.get(priority or "P3", "低")


def status_label(status: str | None) -> str:
    return STATUS_LABELS.get(status or "unknown", "未知")


def alert_status_label(status: str | None) -> str:
    return ALERT_STATUS_LABELS.get(status or "unread", "未读")


def format_score(score: float | int | None) -> str:
    if score is None:
        return "-"
    return str(int(round(float(score))))


def risk_text(priority: str | None) -> str:
    if priority == "P0":
        return "严重风险"
    if priority == "P1":
        return "高关注"
    if priority == "P2":
        return "中等关注"
    return "低关注"


def truncate_text(text: str | None, limit: int = 140) -> str:
    value = " ".join((text or "").split())
    if len(value) <= limit:
        return value or "-"
    return f"{value[: limit - 1]}…"


def selected_id(table: QTableWidget) -> int | None:
    row = table.currentRow()
    if row < 0:
        return None
    item = table.item(row, 0)
    if item is None:
        return None
    value = item.data(Qt.ItemDataRole.UserRole)
    return int(value) if value is not None else None


def set_table_rows(table: QTableWidget, headers: list[str], rows: list[list[Any]], ids: list[int] | None = None) -> None:
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setRowCount(len(rows))
    table.setAlternatingRowColors(True)
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            item = QTableWidgetItem("" if value is None else str(value))
            if column_index == 0 and ids:
                item.setData(Qt.ItemDataRole.UserRole, ids[row_index])
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row_index, column_index, item)
    table.resizeColumnsToContents()


def clear_layout(layout: QVBoxLayout | QHBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        if child_layout is not None:
            clear_layout(child_layout)


def make_scroll_area() -> tuple[QScrollArea, QWidget, QVBoxLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    scroll.setWidget(content)
    return scroll, content, layout


def info(parent: object, message: str) -> None:
    QMessageBox.information(parent, "提示", message)


def warn(parent: object, message: str) -> None:
    QMessageBox.warning(parent, "错误", message)


class Card(QFrame):
    def __init__(self, object_name: str = "Card") -> None:
        super().__init__()
        self.setObjectName(object_name)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)


class PriorityBadge(QLabel):
    def __init__(self, priority: str | None) -> None:
        super().__init__(priority_label(priority))
        value = priority or "P3"
        self.setObjectName(f"PriorityBadge{value}")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class StatusBadge(QLabel):
    def __init__(self, status: str | None) -> None:
        super().__init__(status_label(status))
        self.setObjectName("StatusBadge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class ScorePill(QLabel):
    def __init__(self, label: str, score: float | int | None) -> None:
        super().__init__(f"{label} {format_score(score)}")
        self.setObjectName("ScorePill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class MetricCard(Card):
    def __init__(self, title: str, value: str | int = "0", subtitle: str = "") -> None:
        super().__init__("MetricCard")
        self.title = QLabel(title)
        self.title.setObjectName("MetricTitle")
        self.value = QLabel(str(value))
        self.value.setObjectName("MetricValue")
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("MutedText")
        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        if subtitle:
            layout.addWidget(self.subtitle)

    def set_value(self, value: str | int, subtitle: str = "") -> None:
        self.value.setText(str(value))
        self.subtitle.setText(subtitle)
        self.subtitle.setVisible(bool(subtitle))


class EmptyState(Card):
    def __init__(
        self,
        title: str,
        message: str,
        primary_text: str | None = None,
        primary_action: Callable[[], None] | None = None,
        secondary_text: str | None = None,
        secondary_action: Callable[[], None] | None = None,
        tertiary_text: str | None = None,
        tertiary_action: Callable[[], None] | None = None,
    ) -> None:
        super().__init__("EmptyState")
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setObjectName("EmptyTitle")
        body = QLabel(message)
        body.setObjectName("MutedText")
        body.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(body)
        buttons = QHBoxLayout()
        if primary_text and primary_action:
            primary = QPushButton(primary_text)
            primary.setObjectName("PrimaryButton")
            primary.clicked.connect(primary_action)
            buttons.addWidget(primary)
        if secondary_text and secondary_action:
            secondary = QPushButton(secondary_text)
            secondary.clicked.connect(secondary_action)
            buttons.addWidget(secondary)
        if tertiary_text and tertiary_action:
            tertiary = QPushButton(tertiary_text)
            tertiary.clicked.connect(tertiary_action)
            buttons.addWidget(tertiary)
        buttons.addStretch()
        layout.addLayout(buttons)


class GlobalCompanySearchBox(QWidget):
    def __init__(
        self,
        db: DatabaseManager,
        *,
        on_company_open: Callable[[int], None] | None = None,
        on_added: Callable[[int], None] | None = None,
        on_query_changed: Callable[[str], None] | None = None,
        on_submit: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self.db = db
        self.on_company_open = on_company_open
        self.on_added = on_added
        self.on_query_changed = on_query_changed
        self.on_submit = on_submit
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.input = QLineEdit()
        self.input.setPlaceholderText("搜索公司、代码、简称、品牌...")
        self.input.textChanged.connect(self._query_changed)
        self.input.returnPressed.connect(self._submit)
        layout.addWidget(self.input)

    def text(self) -> str:
        return self.input.text()

    def setText(self, value: str) -> None:
        self.input.setText(value)

    def focus(self) -> None:  # type: ignore[override]
        self.input.setFocus()

    def _query_changed(self, text: str) -> None:
        query = text.strip()
        if query and self.on_query_changed:
            self.on_query_changed(query)

    def _submit(self) -> None:
        query = self.input.text().strip()
        if self.on_submit:
            self.on_submit(query)
        elif query and self.on_query_changed:
            self.on_query_changed(query)


class SelfSelectedCompanyCard(Card):
    def __init__(
        self,
        *,
        name: str,
        ticker: str,
        exchange: str,
        country: str,
        industry: str,
        risk_priority: str,
        unread_alerts: int,
        new_event_count: int,
        latest_event_title: str,
        last_scanned_text: str,
        source_status: str,
        on_open: Callable[[], None],
        on_scan: Callable[[], None],
        on_remove: Callable[[], None],
    ) -> None:
        super().__init__("CompanyCard")
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel(name)
        title.setObjectName("CardTitle")
        meta = QLabel(" / ".join(item for item in [ticker, exchange, country, industry] if item) or "本地公司")
        meta.setObjectName("MutedText")
        meta.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(meta)
        top.addLayout(title_box, 1)
        top.addWidget(PriorityBadge(risk_priority))

        stats = QHBoxLayout()
        for label, value in [
            ("未读", str(unread_alerts)),
            ("7天事件", str(new_event_count)),
            ("来源", source_status),
            ("扫描", last_scanned_text),
        ]:
            pill = QLabel(f"{label} {value}")
            pill.setObjectName("ScorePill")
            stats.addWidget(pill)
        stats.addStretch()
        top.addLayout(stats, 2)

        actions = QHBoxLayout()
        for text, callback, primary in [
            ("查看详情", on_open, True),
            ("立即扫描", on_scan, False),
            ("删除自选", on_remove, False),
        ]:
            button = QPushButton(text)
            if primary:
                button.setObjectName("PrimaryButton")
            button.clicked.connect(callback)
            actions.addWidget(button)
        top.addLayout(actions)
        layout.addLayout(top)

        latest = QLabel(f"{risk_text(risk_priority)} · 最新事件：{truncate_text(latest_event_title, 160)}")
        latest.setObjectName("MutedText")
        latest.setWordWrap(True)
        layout.addWidget(latest)


class HotCompanyCard(Card):
    def __init__(
        self,
        candidate: HotCompanyCandidate,
        *,
        on_add: Callable[[HotCompanyCandidate], None],
        on_view: Callable[[HotCompanyCandidate], None],
    ) -> None:
        super().__init__("HotCompanyCard")
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        title = QLabel(candidate.name)
        title.setObjectName("CardTitle")
        top.addWidget(title, 1)
        hot = QLabel(f"热度 {candidate.hot_level}")
        hot.setObjectName("HotBadge")
        top.addWidget(hot)
        layout.addLayout(top)
        meta = QLabel(" / ".join(item for item in [candidate.ticker, candidate.exchange, candidate.industry] if item) or "热门候选")
        meta.setObjectName("MutedText")
        layout.addWidget(meta)
        reason = QLabel("、".join(candidate.reasons) or "最近被频繁提及")
        reason.setObjectName("MutedText")
        reason.setWordWrap(True)
        layout.addWidget(reason)
        actions = QHBoxLayout()
        add_btn = QPushButton("已在自选" if candidate.already_watchlisted else "加入自选")
        add_btn.setObjectName("PrimaryButton")
        add_btn.setEnabled(not candidate.already_watchlisted)
        add_btn.clicked.connect(lambda: on_add(candidate))
        view_btn = QPushButton("查看相关动态")
        view_btn.clicked.connect(lambda: on_view(candidate))
        actions.addWidget(add_btn)
        actions.addWidget(view_btn)
        actions.addStretch()
        layout.addLayout(actions)


class CompanySummaryHeader(Card):
    def __init__(self) -> None:
        super().__init__("HeaderCard")
        self.layout = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setObjectName("DetailHeader")
        self.meta = QLabel()
        self.meta.setObjectName("MutedText")
        self.stats = QLabel()
        self.stats.setObjectName("MutedText")
        self.layout.addWidget(self.title)
        self.layout.addWidget(self.meta)
        self.layout.addWidget(self.stats)

    def set_summary(
        self,
        *,
        name: str,
        ticker: str,
        exchange: str,
        risk: str,
        unread_alerts: int,
        events: int,
        last_scan: str,
    ) -> None:
        self.title.setText(name)
        self.meta.setText(" / ".join(item for item in [ticker, exchange, risk] if item))
        self.stats.setText(f"未读告警 {unread_alerts} · 事件 {events} · 最近扫描 {last_scan}")


class RemoveWatchlistConfirmDialog:
    @staticmethod
    def confirm(parent: object, company_name: str) -> bool:
        result = QMessageBox.question(
            parent,
            "删除自选",
            f"确定将「{company_name}」从自选公司移除吗？\n\n历史文档、事件和告警会保留，不会被删除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes


class CompanyCard(Card):
    def __init__(
        self,
        *,
        name: str,
        ticker: str,
        exchange: str,
        risk_priority: str,
        unread_alerts: int,
        aliases_count: int,
        latest_event_title: str,
        last_scanned_text: str,
        on_open: Callable[[], None],
        on_alias: Callable[[], None],
        on_scan: Callable[[], None],
    ) -> None:
        super().__init__("CompanyCard")
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        title = QLabel(name)
        title.setObjectName("CardTitle")
        meta = QLabel(" / ".join(item for item in [ticker, exchange] if item) or "未设置代码")
        meta.setObjectName("MutedText")
        title_box = QVBoxLayout()
        title_box.addWidget(title)
        title_box.addWidget(meta)
        top.addLayout(title_box)
        top.addStretch()
        top.addWidget(PriorityBadge(risk_priority))
        layout.addLayout(top)

        details = QLabel(
            f"{risk_text(risk_priority)} · 未读告警 {unread_alerts} · 别名 {aliases_count} · 最近扫描 {last_scanned_text}"
        )
        details.setObjectName("MutedText")
        details.setWordWrap(True)
        layout.addWidget(details)
        latest = QLabel(f"最新事件：{truncate_text(latest_event_title, 90)}")
        latest.setWordWrap(True)
        layout.addWidget(latest)

        actions = QHBoxLayout()
        for text, callback in [("打开详情", on_open), ("添加别名", on_alias), ("立即扫描", on_scan)]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)


class EventCard(Card):
    def __init__(
        self,
        *,
        company_name: str,
        priority: str,
        title: str,
        event_type: str,
        event_status: str,
        confidence_score: float,
        materiality_score: float,
        source_label: str,
        created_text: str,
        evidence: str,
        on_evidence: Callable[[], None],
        on_company: Callable[[], None] | None,
        on_detail: Callable[[], None],
        on_ack: Callable[[], None] | None = None,
        on_delete: Callable[[], None] | None = None,
    ) -> None:
        super().__init__("EventCard")
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(PriorityBadge(priority))
        heading = QLabel(f"{company_name} · {title}")
        heading.setObjectName("CardTitle")
        heading.setWordWrap(True)
        top.addWidget(heading, 1)
        top.addWidget(ScorePill("重大性", materiality_score))
        top.addWidget(ScorePill("置信度", confidence_score))
        layout.addLayout(top)
        meta = QLabel(f"{event_type} · {status_label(event_status)} · {source_label} · {created_text}")
        meta.setObjectName("MutedText")
        layout.addWidget(meta)
        snippet = QLabel(truncate_text(evidence, 220))
        snippet.setWordWrap(True)
        layout.addWidget(snippet)
        actions = QHBoxLayout()
        action_items: list[tuple[str, Callable[[], None]]] = [("查看证据", on_evidence), ("详情", on_detail)]
        if on_company:
            action_items.insert(1, ("打开公司", on_company))
        for text, callback in action_items:
            button = QPushButton(text)
            button.clicked.connect(callback)
            actions.addWidget(button)
        if on_ack:
            ack = QPushButton("标记已读")
            ack.clicked.connect(on_ack)
            actions.addWidget(ack)
        if on_delete:
            delete_btn = QPushButton("删除事件")
            delete_btn.setObjectName("DangerButton")
            delete_btn.clicked.connect(on_delete)
            actions.addWidget(delete_btn)
        actions.addStretch()
        layout.addLayout(actions)


class AlertCard(Card):
    def __init__(
        self,
        *,
        company_name: str,
        priority: str,
        title: str,
        message: str,
        status: str,
        confidence_score: float,
        materiality_score: float,
        created_text: str,
        evidence: str,
        on_evidence: Callable[[], None],
        on_ack: Callable[[], None],
        on_ignore: Callable[[], None],
        on_company: Callable[[], None] | None,
        on_delete: Callable[[], None] | None = None,
    ) -> None:
        super().__init__("AlertCardSubdued" if status != "unread" else "AlertCard")
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(PriorityBadge(priority))
        title_label = QLabel(f"{company_name} · {title}")
        title_label.setObjectName("CardTitle")
        title_label.setWordWrap(True)
        top.addWidget(title_label, 1)
        top.addWidget(ScorePill("重大性", materiality_score))
        top.addWidget(ScorePill("置信度", confidence_score))
        layout.addLayout(top)
        meta = QLabel(f"{alert_status_label(status)} · {created_text}")
        meta.setObjectName("MutedText")
        layout.addWidget(meta)
        body = QLabel(truncate_text(message, 180))
        body.setWordWrap(True)
        layout.addWidget(body)
        snippet = QLabel(f"证据：{truncate_text(evidence, 180)}")
        snippet.setObjectName("EvidenceText")
        snippet.setWordWrap(True)
        layout.addWidget(snippet)
        actions = QHBoxLayout()
        action_items: list[tuple[str, Callable[[], None]]] = [
            ("查看证据", on_evidence),
            ("标记已读", on_ack),
            ("忽略", on_ignore),
        ]
        if on_company:
            action_items.append(("打开公司", on_company))
        for text, callback in action_items:
            button = QPushButton(text)
            button.clicked.connect(callback)
            actions.addWidget(button)
        if on_delete:
            delete_btn = QPushButton("删除告警")
            delete_btn.setObjectName("DangerButton")
            delete_btn.clicked.connect(on_delete)
            actions.addWidget(delete_btn)
        actions.addStretch()
        layout.addLayout(actions)


class TextViewerDialog(QDialog):
    def __init__(self, title: str, text: str, parent: object | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(860, 640)
        layout = QVBoxLayout(self)
        editor = QTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(text)
        layout.addWidget(editor)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class EvidenceDialog(TextViewerDialog):
    def __init__(self, title: str, snippets: list[str], parent: object | None = None) -> None:
        text = "\n\n---\n\n".join(snippets) if snippets else "暂无证据片段"
        super().__init__(title, text, parent)


class MetricBox(MetricCard):
    def __init__(self, title: str, value: str = "0") -> None:
        super().__init__(title, value)


def toolbar(*buttons: QPushButton) -> QHBoxLayout:
    layout = QHBoxLayout()
    for button in buttons:
        layout.addWidget(button)
    layout.addStretch()
    return layout
