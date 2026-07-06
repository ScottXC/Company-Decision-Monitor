from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop import PREVIEW_MODE_LABEL


def show_preview_message(parent: QWidget, title: str = "功能占位") -> None:
    QMessageBox.information(
        parent,
        title,
        "当前版本为 UI Preview Mode，仅展示页面结构和交互占位。\n"
        "尚未接入真实 API、联网搜索、爬虫、数据库写入或业务计算。",
    )


class SectionCard(QFrame):
    def __init__(self, title: str | None = None, subtitle: str | None = None) -> None:
        super().__init__()
        self.setObjectName("SectionCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(10)
        if title:
            header = QHBoxLayout()
            title_label = QLabel(title)
            title_label.setObjectName("SectionTitle")
            header.addWidget(title_label)
            header.addStretch()
            self.layout.addLayout(header)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("MutedText")
            subtitle_label.setWordWrap(True)
            self.layout.addWidget(subtitle_label)


class PageHeader(QWidget):
    def __init__(
        self,
        title: str,
        subtitle: str,
        *,
        primary_text: str | None = None,
        primary_action: Callable[[], None] | None = None,
        secondary_text: str | None = None,
        secondary_action: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        text_box = QVBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("HeroTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("MutedText")
        subtitle_label.setWordWrap(True)
        text_box.addWidget(title_label)
        text_box.addWidget(subtitle_label)
        layout.addLayout(text_box, 1)
        if secondary_text and secondary_action:
            secondary = QPushButton(secondary_text)
            secondary.clicked.connect(secondary_action)
            layout.addWidget(secondary)
        if primary_text and primary_action:
            primary = QPushButton(primary_text)
            primary.setObjectName("PrimaryButton")
            primary.clicked.connect(primary_action)
            layout.addWidget(primary)


class StatusBadge(QLabel):
    def __init__(self, text: str, tone: str = "neutral") -> None:
        super().__init__(text)
        self.setObjectName(f"StatusBadge-{tone}")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class MetricCard(SectionCard):
    def __init__(self, title: str, value: str, subtitle: str) -> None:
        super().__init__()
        self.setObjectName("MetricCard")
        self.layout.addWidget(_label(title, "MetricTitle"))
        self.layout.addWidget(_label(value, "MetricValue"))
        body = _label(subtitle, "MutedText")
        body.setWordWrap(True)
        self.layout.addWidget(body)


class EmptyState(SectionCard):
    def __init__(
        self,
        title: str,
        message: str,
        *,
        action_text: str | None = None,
        action: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("EmptyState")
        self.layout.addWidget(_label(title, "EmptyTitle"))
        body = _label(message, "MutedText")
        body.setWordWrap(True)
        self.layout.addWidget(body)
        if action_text and action:
            row = QHBoxLayout()
            button = QPushButton(action_text)
            button.setObjectName("PrimaryButton")
            button.clicked.connect(action)
            row.addWidget(button)
            row.addStretch()
            self.layout.addLayout(row)


class LoadingState(SectionCard):
    def __init__(self, message: str = "正在加载界面占位...") -> None:
        super().__init__()
        self.setObjectName("LoadingState")
        self.layout.addWidget(_label(message, "MutedText"))


class PreviewNotice(SectionCard):
    def __init__(self) -> None:
        super().__init__("当前模式", "当前版本仅为正式产品 UI 雏形：不接入真实 API，不执行联网搜索，不写入真实业务数据。")
        self.setObjectName("PreviewNotice")
        self.layout.addWidget(StatusBadge(PREVIEW_MODE_LABEL, "info"))


class PlaceholderChart(SectionCard):
    def __init__(self, title: str, message: str) -> None:
        super().__init__(title, message)
        chart = QFrame()
        chart.setObjectName("PlaceholderChart")
        chart.setMinimumHeight(140)
        chart_layout = QGridLayout(chart)
        chart_layout.addWidget(_label("等待数据源接入", "MutedText"), 0, 0, Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(chart)


class PlaceholderTable(SectionCard):
    def __init__(self, title: str, headers: Sequence[str], empty_message: str) -> None:
        super().__init__(title)
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(list(headers))
        table.setAlternatingRowColors(True)
        table.setMinimumHeight(140)
        for column, header in enumerate(headers):
            item = QTableWidgetItem(header)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setHorizontalHeaderItem(column, item)
        self.layout.addWidget(table)
        note = _label(empty_message, "MutedText")
        note.setWordWrap(True)
        self.layout.addWidget(note)


def metric_grid(cards: Sequence[MetricCard], columns: int = 4) -> QWidget:
    widget = QWidget()
    layout = QGridLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setHorizontalSpacing(12)
    layout.setVerticalSpacing(12)
    for index, card in enumerate(cards):
        layout.addWidget(card, index // columns, index % columns)
    return widget


def scroll_container() -> tuple[QScrollArea, QWidget, QVBoxLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(14)
    scroll.setWidget(content)
    return scroll, content, layout


def _label(text: str, object_name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    return label
