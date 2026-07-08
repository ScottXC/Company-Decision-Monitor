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
}

CATEGORY_LABELS = {
    "global": "公开实体",
    "registry": "注册信息",
    "financial": "上市证券",
    "news": "新闻媒体",
    "fallback": "补充来源",
    "external_link": "外部链接",
}


def show_preview_message(parent: QWidget, title: str = "当前模式") -> None:
    QMessageBox.information(
        parent,
        title,
        "当前版本为 Public + Free API Network Mode。\n"
        "软件会优先使用公开数据源；部分增强来源需要用户自行配置免费 API key。"
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
        self.layout.setContentsMargins(16, 14, 16, 14)
        self.layout.setSpacing(9)
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
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
        layout.addLayout(text_box)
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
        actions.addStretch()
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
    def __init__(self, message: str = "正在加载公开数据源...") -> None:
        super().__init__()
        self.setObjectName("LoadingState")
        self.layout.addWidget(_label(message, "MutedText"))


class PreviewNotice(SectionCard):
    def __init__(self) -> None:
        super().__init__(
            "当前模式",
            "正在使用公开数据源和用户配置的免费 API key。未配置的数据源会自动跳过；网络或 provider 不可用时显示错误状态，不伪造数据。",
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
        key.setFixedWidth(118)
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
    layout.setSpacing(16)
    scroll.setWidget(content)
    return scroll, content, layout


def _label(text: str, object_name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    return label
