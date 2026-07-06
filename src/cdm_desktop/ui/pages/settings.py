from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop import PREVIEW_MODE_LABEL, PRODUCT_NAME_ZH, __version__
from cdm_desktop.paths import AppPaths
from cdm_desktop.ui.components import (
    PageHeader,
    PreviewNotice,
    SectionCard,
    scroll_container,
    show_preview_message,
)


class SettingsPage(QWidget):
    route = "/settings"
    page_title = "设置 Settings"

    def __init__(self, navigate: Callable[[str], None], paths: AppPaths | None = None) -> None:
        super().__init__()
        self.navigate = navigate
        self.paths = paths
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, layout = scroll_container()
        root.addWidget(scroll)
        layout.addWidget(
            PageHeader(
                "设置",
                "管理主题、数据源占位、LLM 占位、缓存占位和应用信息。",
            )
        )
        layout.addWidget(PreviewNotice())

        app_info = SectionCard("应用信息")
        form = QFormLayout()
        form.addRow("应用名称", QLabel(PRODUCT_NAME_ZH))
        form.addRow("当前模式", QLabel(PREVIEW_MODE_LABEL))
        form.addRow("版本号", QLabel(__version__))
        if paths:
            form.addRow("本地数据目录", QLabel(str(paths.app_data_dir)))
        app_info.layout.addLayout(form)
        layout.addWidget(app_info)

        theme = SectionCard("主题设置占位")
        theme_row = QHBoxLayout()
        for label in ["跟随系统", "浅色金融终端", "深色金融终端"]:
            checkbox = QCheckBox(label)
            checkbox.setEnabled(False)
            checkbox.setToolTip("UI 占位：主题切换将在后续版本接入")
            theme_row.addWidget(checkbox)
        theme_row.addStretch()
        theme.layout.addLayout(theme_row)
        layout.addWidget(theme)

        data = SectionCard("数据源设置占位", "当前版本未接入真实 API、真实联网搜索或真实爬虫。")
        for text in ["配置公司搜索源", "配置新闻源", "配置公告源", "测试数据连接"]:
            button = QPushButton(text)
            button.setEnabled(False)
            button.setToolTip("UI Preview Mode：暂未接入真实数据源")
            data.layout.addWidget(button)
        layout.addWidget(data)

        llm = SectionCard("LLM 设置占位", "当前不调用任何 LLM，不需要 API key。未来仅用于摘要和解释，不参与事实识别。")
        llm_button = QPushButton("配置 LLM 摘要")
        llm_button.clicked.connect(lambda: show_preview_message(self, "LLM 设置"))
        llm.layout.addWidget(llm_button)
        layout.addWidget(llm)

        cache = SectionCard("缓存清理占位")
        cache_button = QPushButton("清理 UI 缓存")
        cache_button.clicked.connect(lambda: show_preview_message(self, "缓存清理"))
        cache.layout.addWidget(cache_button)
        layout.addWidget(cache)

        note = SectionCard("开发状态说明")
        note.layout.addWidget(
            QLabel(
                "当前版本仅包含正式软件界面雏形：不包含真实公司数据、不接入 API、"
                "不执行真实联网搜索、不运行真实爬虫、不提供投资建议。"
            )
        )
        layout.addWidget(note)
        layout.addStretch()
