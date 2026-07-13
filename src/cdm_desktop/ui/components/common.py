from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop import APP_MODE_LABEL
from cdm_desktop.public_api.models import ProviderStatus

STATE_LABELS = {
    "enabled": "可用",
    "not_configured": "未配置",
    "disabled": "暂未接入",
    "failed": "异常",
    "rate_limited": "限流",
    "quota_exceeded": "额度已用完",
    "premium_endpoint": "高级端点不可用",
    "invalid_key": "Key 可能无效",
    "empty": "无结果",
    "network_timeout": "请求超时",
    "dns_failure": "网络不可用",
    "http_error": "服务错误",
    "parse_error": "解析失败",
    "provider_unavailable": "来源不可用",
    "cache_miss": "无缓存",
    "dependency_missing": "依赖未安装",
    "index_missing": "索引缺失",
    "index_corrupted": "索引损坏",
}

STATE_TONES = {
    "enabled": "success",
    "not_configured": "warning",
    "disabled": "neutral",
    "failed": "danger",
    "rate_limited": "warning",
    "quota_exceeded": "warning",
    "premium_endpoint": "warning",
    "invalid_key": "danger",
    "empty": "neutral",
    "network_timeout": "warning",
    "dns_failure": "warning",
    "http_error": "danger",
    "parse_error": "danger",
    "provider_unavailable": "danger",
    "cache_miss": "neutral",
    "dependency_missing": "warning",
    "index_missing": "danger",
    "index_corrupted": "danger",
}

CATEGORY_LABELS = {
    "global": "公开实体",
    "registry": "注册信息",
    "financial": "上市证券",
    "news": "新闻媒体",
    "fallback": "补充来源",
    "external_link": "外部链接",
    "symbol_universe": "证券目录",
    "experimental": "实验来源",
    "web_evidence": "网页证据",
}


def show_preview_message(parent: QWidget, title: str = "当前模式") -> None:
    QMessageBox.information(
        parent,
        title,
        f"当前版本为 {APP_MODE_LABEL}。\n"
        "普通用户默认无需申请 API key；软件会优先使用开源项目组合和公开无 key 数据源。"
        "未配置的来源会自动跳过，不会显示伪造公司、新闻或财务数据。",
    )


def friendly_state_label(state: str) -> str:
    return STATE_LABELS.get(state, "未知")


def friendly_state_tone(state: str) -> str:
    return STATE_TONES.get(state, "neutral")


def friendly_category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category or "其他")


def provider_status_summary(statuses: Sequence[ProviderStatus]) -> dict[str, str]:
    grouped: dict[str, list[ProviderStatus]] = {}
    for status in statuses:
        grouped.setdefault(status.category, []).append(status)
    summary: dict[str, str] = {}
    for category, items in grouped.items():
        enabled = sum(1 for item in items if item.state in {"enabled", "empty"})
        failed = sum(1 for item in items if item.state in {"failed", "invalid_key", "rate_limited"})
        missing = sum(1 for item in items if item.state == "not_configured")
        if failed and enabled:
            value = "部分可用"
        elif failed:
            value = "异常"
        elif enabled:
            value = "正常"
        elif missing:
            value = "未配置"
        else:
            value = "暂未接入"
        summary[category] = value
    return summary


def sanitize_error_message(message: str) -> str:
    blocked = ("Traceback", "Exception", "JSONDecodeError", "HTTPError", "NoneType")
    if any(token in message for token in blocked):
        return "该数据源暂时不可用，已继续尝试其他来源。"
    return message.strip() or "该数据源暂时不可用。"


class SectionCard(QFrame):
    def __init__(self, title: str | None = None, subtitle: str | None = None) -> None:
        super().__init__()
        self.setObjectName("SectionCard")
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 8, 0, 8)
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
            subtitle_label.setMinimumWidth(0)
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
        layout.setSpacing(20)
        text_box = QVBoxLayout()
        text_box.setSpacing(5)
        title_label = QLabel(title)
        title_label.setObjectName("HeroTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("MutedText")
        subtitle_label.setWordWrap(True)
        subtitle_label.setMinimumWidth(0)
        text_box.addWidget(title_label)
        text_box.addWidget(subtitle_label)
        layout.addLayout(text_box, 1)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        if secondary_text and secondary_action:
            secondary = QPushButton(secondary_text)
            secondary.clicked.connect(secondary_action)
            actions.addWidget(secondary)
        if primary_text and primary_action:
            primary = QPushButton(primary_text)
            primary.setObjectName("PrimaryButton")
            primary.clicked.connect(primary_action)
            actions.addWidget(primary)
        if secondary_text or primary_text:
            layout.addLayout(actions)


class StatusBadge(QLabel):
    def __init__(self, text: str, tone: str = "neutral") -> None:
        super().__init__(text)
        self.setObjectName(f"StatusBadge-{tone}")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(0)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)


class MetricCard(SectionCard):
    def __init__(self, title: str, value: str, subtitle: str) -> None:
        super().__init__()
        self.setObjectName("MetricCard")
        self.layout.setContentsMargins(16, 14, 16, 14)
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
        self.layout.setContentsMargins(22, 22, 22, 22)
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
    def __init__(self, message: str = "正在加载公开数据源...") -> None:
        super().__init__()
        self.setObjectName("LoadingState")
        self.layout.setContentsMargins(18, 16, 18, 16)
        self.layout.addWidget(_label(message, "MutedText"))


class PreviewNotice(SectionCard):
    def __init__(self) -> None:
        super().__init__(
            "当前模式",
            "默认使用开源项目组合和公开无 key 数据源。高级 API provider 默认关闭；网络或 provider 不可用时显示错误状态，不伪造数据。",
        )
        self.setObjectName("PreviewNotice")
        self.layout.addWidget(StatusBadge(APP_MODE_LABEL, "info"))


class HeroPanel(SectionCard):
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
        self.setObjectName("HeroPanel")
        title_label = QLabel(title)
        title_label.setObjectName("HeroTitle")
        title_label.setWordWrap(True)
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("HeroSubtitle")
        subtitle_label.setWordWrap(True)
        subtitle_label.setMinimumWidth(0)
        self.layout.addWidget(title_label)
        self.layout.addWidget(subtitle_label)
        if primary_text or secondary_text:
            actions = QHBoxLayout()
            actions.setSpacing(10)
            if primary_text and primary_action:
                primary = QPushButton(primary_text)
                primary.setObjectName("PrimaryButton")
                primary.clicked.connect(primary_action)
                actions.addWidget(primary)
            if secondary_text and secondary_action:
                secondary = QPushButton(secondary_text)
                secondary.clicked.connect(secondary_action)
                actions.addWidget(secondary)
            actions.addStretch()
            self.layout.addLayout(actions)


class ActionTile(SectionCard):
    def __init__(self, title: str, subtitle: str, button_text: str, action: Callable[[], None]) -> None:
        super().__init__()
        self.setObjectName("ActionTile")
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        body = QLabel(subtitle)
        body.setObjectName("MutedText")
        body.setWordWrap(True)
        button = QPushButton(button_text)
        button.clicked.connect(action)
        self.layout.addWidget(title_label)
        self.layout.addWidget(body)
        self.layout.addWidget(button)


class InfoRow(QWidget):
    def __init__(self, label: str, value: str | None) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        key = QLabel(label)
        key.setObjectName("FieldLabel")
        key.setFixedWidth(132)
        val = QLabel(value or "暂无数据")
        val.setObjectName("FieldValue")
        val.setWordWrap(True)
        val.setMinimumWidth(0)
        layout.addWidget(key)
        layout.addWidget(val, 1)


class DetailGrid(QWidget):
    def __init__(self, fields: Sequence[tuple[str, str | None]], columns: int = 2) -> None:
        super().__init__()
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        actual_columns = 1
        for index, (label, value) in enumerate(fields):
            layout.addWidget(InfoRow(label, value), index // actual_columns, index % actual_columns)


class CollapsibleSection(SectionCard):
    def __init__(self, title: str, subtitle: str | None = None, *, expanded: bool = False) -> None:
        super().__init__()
        self._expanded = expanded
        self.toggle = QPushButton(("收起 " if expanded else "展开 ") + title)
        self.toggle.setObjectName("LinkButton")
        self.toggle.clicked.connect(self._toggle)
        self.layout.addWidget(self.toggle)
        if subtitle:
            note = _label(subtitle, "MutedText")
            note.setWordWrap(True)
            self.layout.addWidget(note)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 6, 0, 0)
        self.body_layout.setSpacing(8)
        self.body.setVisible(expanded)
        self.layout.addWidget(self.body)

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self.body.setVisible(self._expanded)
        text = self.toggle.text()
        title = text.replace("展开 ", "").replace("收起 ", "")
        self.toggle.setText(("收起 " if self._expanded else "展开 ") + title)


class Divider(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.HLine)
        self.setObjectName("Divider")
        self.setFixedHeight(1)


class CompanyAvatar(QLabel):
    def __init__(self, name: str) -> None:
        initial = next((char.upper() for char in name.strip() if char.isalnum()), "C")
        super().__init__(initial)
        self.setObjectName("Avatar")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(40, 40)


class IconButton(QToolButton):
    def __init__(self, *, tooltip: str, standard_icon: QStyle.StandardPixmap) -> None:
        super().__init__()
        self.setIcon(self.style().standardIcon(standard_icon))
        self.setIconSize(QSize(17, 17))
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setFixedSize(36, 36)


class ListRow(QFrame):
    activated = Signal()

    def __init__(
        self,
        title: str,
        subtitle: str,
        *,
        detail: str | None = None,
        source: str | None = None,
        action_tooltip: str | None = None,
        action: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("ListRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(12)
        layout.addWidget(CompanyAvatar(title))
        text = QVBoxLayout()
        text.setSpacing(3)
        heading = QLabel(title)
        heading.setObjectName("ListTitle")
        heading.setWordWrap(True)
        meta = QLabel(subtitle)
        meta.setObjectName("MutedText")
        meta.setWordWrap(True)
        text.addWidget(heading)
        text.addWidget(meta)
        if detail:
            description = QLabel(detail)
            description.setObjectName("Caption")
            description.setWordWrap(True)
            description.setMaximumHeight(38)
            text.addWidget(description)
        layout.addLayout(text, 1)
        if source:
            layout.addWidget(StatusBadge(source, "neutral"))
        if action and action_tooltip:
            button = IconButton(tooltip=action_tooltip, standard_icon=QStyle.StandardPixmap.SP_DialogYesButton)
            button.clicked.connect(action)
            layout.addWidget(button)
        arrow = IconButton(tooltip="查看详情", standard_icon=QStyle.StandardPixmap.SP_ArrowForward)
        arrow.clicked.connect(self.activated.emit)
        layout.addWidget(arrow)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
        super().mouseReleaseEvent(event)


class NewsRow(QFrame):
    def __init__(
        self,
        title: str,
        meta: str,
        snippet: str | None,
        *,
        open_action: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("ListRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(12)
        text = QVBoxLayout()
        text.setSpacing(4)
        heading = QLabel(title)
        heading.setObjectName("ListTitle")
        heading.setWordWrap(True)
        source = QLabel(meta)
        source.setObjectName("Caption")
        text.addWidget(heading)
        text.addWidget(source)
        if snippet:
            body = QLabel(snippet[:260])
            body.setObjectName("MutedText")
            body.setWordWrap(True)
            body.setMaximumHeight(42)
            text.addWidget(body)
        layout.addLayout(text, 1)
        if open_action:
            button = IconButton(tooltip="打开原文", standard_icon=QStyle.StandardPixmap.SP_ArrowForward)
            button.clicked.connect(open_action)
            layout.addWidget(button)


class MetricCell(QWidget):
    def __init__(self, label: str, value: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 18, 4)
        layout.setSpacing(3)
        key = QLabel(label)
        key.setObjectName("MetricTitle")
        val = QLabel(value)
        val.setObjectName("MetricValue")
        val.setWordWrap(True)
        layout.addWidget(key)
        layout.addWidget(val)


class InlineError(QFrame):
    def __init__(self, message: str, *, retry: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.setObjectName("InlineError")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        label = QLabel(sanitize_error_message(message))
        label.setWordWrap(True)
        layout.addWidget(label, 1)
        if retry:
            button = QPushButton("重试")
            button.clicked.connect(retry)
            layout.addWidget(button)


class PlaceholderChart(SectionCard):
    def __init__(self, title: str, message: str) -> None:
        super().__init__(title, message)
        chart = QFrame()
        chart.setObjectName("PlaceholderChart")
        chart.setMinimumHeight(140)
        chart_layout = QGridLayout(chart)
        chart_layout.addWidget(_label("该模块暂未接入真实 provider 数据。", "MutedText"), 0, 0, Qt.AlignmentFlag.AlignCenter)
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


def provider_status_badge(status: ProviderStatus) -> StatusBadge:
    return StatusBadge(f"{status.display_name} · {friendly_state_label(status.state)}", friendly_state_tone(status.state))


def metric_grid(cards: Sequence[MetricCard], columns: int = 4) -> QWidget:
    widget = QWidget()
    layout = QGridLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setHorizontalSpacing(12)
    layout.setVerticalSpacing(12)
    actual_columns = min(max(columns, 1), 2)
    for index, card in enumerate(cards):
        layout.addWidget(card, index // actual_columns, index % actual_columns)
    return widget


def scroll_container() -> tuple[QScrollArea, QWidget, QVBoxLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    content = QWidget()
    content.setMinimumWidth(0)
    content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(24)
    scroll.setWidget(content)
    return scroll, content, layout


def _label(text: str, object_name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    return label
