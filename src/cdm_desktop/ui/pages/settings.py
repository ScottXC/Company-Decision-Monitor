from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop import APP_MODE_LABEL, PRODUCT_NAME_ZH, __version__
from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.cache import ApiCache
from cdm_desktop.public_api.key_store import ApiKeyStore
from cdm_desktop.public_api.models import ProviderStatus
from cdm_desktop.public_api.registry import ProviderRegistry
from cdm_desktop.public_api.search_service import PublicSearchService
from cdm_desktop.ui.components import (
    DetailGrid,
    PageHeader,
    StatusBadge,
    friendly_category_label,
    friendly_state_label,
    friendly_state_tone,
    sanitize_error_message,
    scroll_container,
)
from cdm_desktop.ui.widgets import ProgressFunctionWorker

RECOMMENDED_KEYS = {"fmp", "alpha_vantage", "marketaux"}


class SettingsPage(QWidget):
    route = "/settings"
    page_title = "数据源设置"

    def __init__(self, navigate: Callable[[str], None], paths: AppPaths | None = None) -> None:
        super().__init__()
        self.navigate = navigate
        self.paths = paths
        self.key_store = ApiKeyStore(paths)
        self.registry = ProviderRegistry()
        self.search_service = PublicSearchService(paths)
        self.cache = ApiCache(paths)
        self.inputs: dict[str, QLineEdit] = {}
        self.thread_pool = QThreadPool.globalInstance()
        self.test_running = False
        self.last_test_statuses: list[ProviderStatus] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, self.layout = scroll_container()
        root.addWidget(scroll)
        self.refresh()

    def refresh(self) -> None:
        self._clear()
        self.layout.addWidget(
            PageHeader(
                "数据源设置",
                "管理免费 API key、公开来源、搜索体验和本地缓存。高级诊断只在需要时展开。",
                primary_text="保存 API key",
                primary_action=self._save_keys,
                secondary_text="测试连接",
                secondary_action=self._test_connections,
            )
        )
        self.layout.addWidget(self._test_progress_panel())

        tabs = QTabWidget()
        tabs.addTab(self._overview_tab(), "总览")
        tabs.addTab(self._keys_tab(), "免费 API key")
        tabs.addTab(self._public_sources_tab(), "公开来源")
        tabs.addTab(self._search_settings_tab(), "搜索")
        tabs.addTab(self._cache_privacy_tab(), "缓存与隐私")
        tabs.addTab(self._about_tab(), "关于")
        self.layout.addWidget(tabs)
        self.layout.addStretch()

    def _test_progress_panel(self) -> QFrame:
        self.test_panel, panel_layout = self._compact_panel("数据源可用性测试")
        self.test_panel.setVisible(self.test_running or bool(self.last_test_statuses))

        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self.test_status_label = QLabel("尚未开始测试。")
        self.test_status_label.setObjectName("MutedText")
        self.test_status_label.setWordWrap(True)
        status_row.addWidget(self.test_status_label, 1)
        self.test_progress = QProgressBar()
        self.test_progress.setFixedWidth(220)
        self.test_progress.setRange(0, 1)
        self.test_progress.setValue(0)
        status_row.addWidget(self.test_progress)
        panel_layout.addLayout(status_row)

        self.test_results = QVBoxLayout()
        self.test_results.setSpacing(6)
        panel_layout.addLayout(self.test_results)
        if self.last_test_statuses:
            self._render_test_results(self.last_test_statuses)
        return self.test_panel

    def _overview_tab(self) -> QWidget:
        page = self._tab_page()
        statuses = self.search_service.provider_statuses()
        configured_keys = sum(1 for item in self.registry.key_definitions() if self.key_store.status(item.key_name)[0])
        available = sum(1 for item in statuses if item.state in {"enabled", "empty"})
        abnormal = sum(1 for item in statuses if item.state in {"failed", "invalid_key", "rate_limited"})

        page.layout().addWidget(
            self._metric_strip(
                [
                    ("可用来源", str(available), "公开来源 + 已配置增强来源"),
                    ("已配置 key", f"{configured_keys} / {len(self.registry.key_definitions())}", "仅显示数量"),
                    ("异常来源", str(abnormal), "局部异常不阻断搜索"),
                    ("最近测试", "按需执行", "点击测试连接更新"),
                ]
            )
        )

        panel, panel_layout = self._compact_panel("数据源状态", "只展示可用、未配置和异常。具体错误在测试结果里展开查看。")
        for status in statuses:
            panel_layout.addWidget(
                self._provider_row(
                    status.display_name,
                    friendly_category_label(status.category),
                    friendly_state_label(status.state),
                    friendly_state_tone(status.state),
                    sanitize_error_message(status.message),
                    "配置" if status.state == "not_configured" else "查看",
                    self._switch_to_keys,
                )
            )
        page.layout().addWidget(panel)
        return page

    def _keys_tab(self) -> QWidget:
        page = self._tab_page()
        self.inputs = {}
        intro, intro_layout = self._compact_panel(
            "免费 API key",
            "Key 只保存在本机 AppData。留空不会覆盖已有 key，界面不会显示明文。",
        )
        intro_layout.addWidget(StatusBadge("可选增强来源", "info"))
        page.layout().addWidget(intro)

        recommended, recommended_layout = self._compact_panel("推荐优先配置")
        optional, optional_layout = self._compact_panel("可选增强来源")
        for definition in self.registry.key_definitions():
            row = self._key_row(
                definition.provider_id,
                definition.key_name,
                definition.label,
                definition.registration_url,
                definition.help_text,
            )
            target = recommended_layout if definition.provider_id in RECOMMENDED_KEYS else optional_layout
            target.addWidget(row)
        page.layout().addWidget(recommended)
        page.layout().addWidget(optional)
        return page

    def _public_sources_tab(self) -> QWidget:
        page = self._tab_page()
        panel, panel_layout = self._compact_panel(
            "无 key 公开来源",
            "这些来源无需填写 API key，但仍可能受网络、限流或字段覆盖影响。",
        )
        status_map = {status.provider_id: status for status in self.search_service.provider_statuses()}
        for provider in [item for item in self.registry.all() if not item.requires_key]:
            status = status_map.get(provider.provider_id)
            state_text = friendly_state_label(status.state) if status else ("已接入" if provider.implemented else "暂未接入")
            state_tone = friendly_state_tone(status.state) if status else ("success" if provider.implemented else "neutral")
            message = sanitize_error_message(status.message) if status else provider.description
            panel_layout.addWidget(
                self._provider_row(
                    provider.display_name,
                    friendly_category_label(provider.category),
                    state_text,
                    state_tone,
                    message,
                    "说明",
                    lambda url=provider.registration_url: QDesktopServices.openUrl(QUrl(url)),
                )
            )
        page.layout().addWidget(panel)
        return page

    def _search_settings_tab(self) -> QWidget:
        page = self._tab_page()
        panel, panel_layout = self._compact_panel("搜索体验", "当前为界面设置项，后续版本会持久化到本地。")
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)

        fuzzy = QCheckBox("启用模糊搜索")
        fuzzy.setChecked(True)
        acronym = QCheckBox("启用缩写匹配")
        acronym.setChecked(True)
        related = QCheckBox("显示可能相关结果")
        related.setChecked(True)
        alias = QCheckBox("启用多语言别名匹配")
        alias.setChecked(True)
        score = QSpinBox()
        score.setRange(50, 95)
        score.setValue(80)
        score.setSuffix(" 分")

        grid.addWidget(fuzzy, 0, 0)
        grid.addWidget(acronym, 0, 1)
        grid.addWidget(related, 1, 0)
        grid.addWidget(alias, 1, 1)
        grid.addWidget(QLabel("最低匹配分数"), 2, 0)
        grid.addWidget(score, 2, 1)
        panel_layout.addLayout(grid)

        note = QLabel("匹配分数越低，结果更多但可能不准确；分数越高，结果更少但更可靠。")
        note.setObjectName("MutedText")
        note.setWordWrap(True)
        panel_layout.addWidget(note)
        page.layout().addWidget(panel)
        return page

    def _cache_privacy_tab(self) -> QWidget:
        page = self._tab_page()
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        cache_panel, cache_layout = self._compact_panel("本地缓存", "用于减少公开数据源请求次数，不会打包进安装包。")
        cache_layout.addWidget(QLabel(f"当前缓存大小：{self.cache.size_bytes() / 1024:.1f} KB"))
        clear_cache = QPushButton("清理缓存")
        clear_cache.setObjectName("DangerButton")
        clear_cache.clicked.connect(self._clear_cache)
        cache_layout.addWidget(clear_cache)

        privacy_panel, privacy_layout = self._compact_panel("隐私说明")
        data_dir = str(self.paths.app_data_dir) if self.paths else "用户 AppData / CompanyDecisionMonitor"
        privacy_layout.addWidget(
            DetailGrid(
                [
                    ("API key 保存位置", f"{data_dir}\\api_keys.json"),
                    ("自选公司保存位置", f"{data_dir}\\watchlist.json"),
                    ("缓存目录", f"{data_dir}\\cache"),
                    ("上传用户配置", "不会上传"),
                    ("安装包包含 key", "不会包含"),
                    ("显示明文 key", "不会显示"),
                ],
                columns=2,
            )
        )
        grid.addWidget(cache_panel, 0, 0)
        grid.addWidget(privacy_panel, 0, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 2)
        wrapper = QWidget()
        wrapper.setLayout(grid)
        page.layout().addWidget(wrapper)
        return page

    def _about_tab(self) -> QWidget:
        page = self._tab_page()
        panel, panel_layout = self._compact_panel("应用信息")
        fields = [
            ("应用名称", PRODUCT_NAME_ZH),
            ("版本", f"v{__version__}"),
            ("模式", APP_MODE_LABEL),
            ("UI 标记", "v0.1.1 UI Polish"),
            ("真实业务边界", "不提供投资建议，不提供交易、买卖、下单、目标价或收益预测。"),
        ]
        if self.paths:
            fields.append(("本地数据目录", str(self.paths.app_data_dir)))
        panel_layout.addWidget(DetailGrid(fields, columns=2))
        page.layout().addWidget(panel)
        return page

    def _key_row(
        self,
        provider_id: str,
        key_name: str,
        label: str,
        registration_url: str,
        help_text: str,
    ) -> QWidget:
        configured, masked = self.key_store.status(key_name)
        row = QWidget()
        row.setObjectName("ProviderRow")
        layout = QGridLayout(row)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(6)

        title = QLabel(label)
        title.setObjectName("ProviderTitle")
        title.setWordWrap(True)
        help_label = QLabel(help_text)
        help_label.setObjectName("MutedText")
        help_label.setWordWrap(True)
        layout.addWidget(title, 0, 0)
        layout.addWidget(help_label, 1, 0)
        layout.addWidget(StatusBadge("已配置" if configured else "未配置", "success" if configured else "warning"), 0, 1)
        layout.addWidget(StatusBadge(provider_id, "neutral"), 1, 1)

        edit = QLineEdit()
        edit.setEchoMode(QLineEdit.EchoMode.Password)
        edit.setPlaceholderText(f"当前：{masked}" if configured else "粘贴免费 API key / token / GUID")
        edit.setMaximumWidth(280)
        self.inputs[key_name] = edit
        layout.addWidget(edit, 0, 2, 2, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        save_btn = QPushButton("保存")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self._save_keys)
        clear_btn = QPushButton("清除")
        clear_btn.setObjectName("DangerButton")
        clear_btn.clicked.connect(lambda _checked=False, key=key_name: self._clear_key(key))
        open_btn = QPushButton("文档")
        open_btn.clicked.connect(lambda _checked=False, url=registration_url: QDesktopServices.openUrl(QUrl(url)))
        buttons.addWidget(save_btn)
        buttons.addWidget(clear_btn)
        buttons.addWidget(open_btn)
        layout.addLayout(buttons, 0, 3, 2, 1)
        layout.setColumnStretch(0, 1)
        return row

    def _provider_row(
        self,
        title_text: str,
        category_text: str,
        state_text: str,
        state_tone: str,
        message_text: str,
        action_text: str | None = None,
        action: Callable[[], None] | None = None,
    ) -> QWidget:
        row = QWidget()
        row.setObjectName("ProviderRow")
        layout = QGridLayout(row)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(4)

        title = QLabel(title_text)
        title.setObjectName("ProviderTitle")
        title.setWordWrap(True)
        message = QLabel(message_text)
        message.setObjectName("MutedText")
        message.setWordWrap(True)
        layout.addWidget(title, 0, 0)
        layout.addWidget(message, 1, 0)
        layout.addWidget(StatusBadge(category_text, "neutral"), 0, 1)
        layout.addWidget(StatusBadge(state_text, state_tone), 0, 2)
        if action_text and action:
            button = QPushButton(action_text)
            button.clicked.connect(action)
            layout.addWidget(button, 0, 3, 2, 1)
        layout.setColumnStretch(0, 1)
        return row

    def _metric_strip(self, metrics: list[tuple[str, str, str]]) -> QWidget:
        strip = QWidget()
        strip.setObjectName("MetricStrip")
        layout = QGridLayout(strip)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)
        for index, (title_text, value_text, subtitle_text) in enumerate(metrics):
            card = QFrame()
            card.setObjectName("MiniMetric")
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(4)
            title = QLabel(title_text)
            title.setObjectName("MetricTitle")
            value = QLabel(value_text)
            value.setObjectName("MetricValue")
            subtitle = QLabel(subtitle_text)
            subtitle.setObjectName("MutedText")
            subtitle.setWordWrap(True)
            card_layout.addWidget(title)
            card_layout.addWidget(value)
            card_layout.addWidget(subtitle)
            layout.addWidget(card, index // 2, index % 2)
        return strip

    def _compact_panel(self, title: str, subtitle: str | None = None) -> tuple[QFrame, QVBoxLayout]:
        panel = QFrame()
        panel.setObjectName("CompactPanel")
        panel.setMinimumWidth(0)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        layout.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("MutedText")
            subtitle_label.setWordWrap(True)
            layout.addWidget(subtitle_label)
        return panel, layout

    def _tab_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)
        return page

    def _save_keys(self) -> None:
        saved = 0
        for key_name, edit in self.inputs.items():
            value = edit.text().strip()
            if value:
                self.key_store.set(key_name, value)
                saved += 1
        QMessageBox.information(self, "API key", f"已保存 {saved} 个本机 key。")
        self.refresh()

    def _clear_key(self, key_name: str) -> None:
        self.key_store.clear(key_name)
        QMessageBox.information(self, "API key", f"已清除 {key_name}。")
        self.refresh()

    def _test_connections(self) -> None:
        if self.test_running:
            QMessageBox.information(self, "测试连接", "数据源测试正在进行，请等待当前测试完成。")
            return
        self.test_running = True
        self.last_test_statuses = []
        self.test_panel.setVisible(True)
        self.test_progress.setRange(0, 1)
        self.test_progress.setValue(0)
        self.test_status_label.setText("准备测试公开数据源和已配置的免费 API provider...")
        self._clear_layout(self.test_results)

        worker = ProgressFunctionWorker(self.search_service.test_provider_connectivity, probe_query="Apple")
        worker.signals.progress.connect(self._update_test_progress)
        worker.signals.finished.connect(self._finish_test_progress)
        worker.signals.error.connect(self._fail_test_progress)
        self.thread_pool.start(worker)

    def _update_test_progress(self, current: int, total: int, message: str) -> None:
        total = max(total, 1)
        current = max(0, min(current, total))
        self.test_progress.setRange(0, total)
        self.test_progress.setValue(current)
        self.test_status_label.setText(f"{message} ({current} / {total})")

    def _finish_test_progress(self, result: object) -> None:
        self.test_running = False
        statuses = result if isinstance(result, list) else []
        self.last_test_statuses = [status for status in statuses if isinstance(status, ProviderStatus)]
        total = len(self.last_test_statuses) or 1
        self.test_progress.setRange(0, total)
        self.test_progress.setValue(total)
        self._render_test_results(self.last_test_statuses)

    def _fail_test_progress(self, message: str) -> None:
        self.test_running = False
        self.test_progress.setRange(0, 1)
        self.test_progress.setValue(0)
        self.test_status_label.setText(sanitize_error_message(message))
        self._clear_layout(self.test_results)
        self.test_results.addWidget(StatusBadge("测试失败", "danger"))

    def _render_test_results(self, statuses: list[ProviderStatus]) -> None:
        self._clear_layout(self.test_results)
        enabled = sum(1 for item in statuses if item.state in {"enabled", "empty"})
        skipped = sum(1 for item in statuses if item.state in {"not_configured", "disabled"})
        failed = sum(1 for item in statuses if item.state in {"failed", "invalid_key", "rate_limited"})
        self.test_status_label.setText(f"测试完成：可用 {enabled}，跳过 {skipped}，异常 {failed}。")

        summary = QHBoxLayout()
        summary.setSpacing(8)
        summary.addWidget(StatusBadge(f"可用 {enabled}", "success"))
        summary.addWidget(StatusBadge(f"跳过 {skipped}", "warning" if skipped else "neutral"))
        summary.addWidget(StatusBadge(f"异常 {failed}", "danger" if failed else "neutral"))
        summary.addStretch()
        self.test_results.addLayout(summary)

        for status in statuses:
            self.test_results.addWidget(
                self._provider_row(
                    status.display_name,
                    friendly_category_label(status.category),
                    friendly_state_label(status.state),
                    friendly_state_tone(status.state),
                    sanitize_error_message(status.message),
                )
            )

    def _clear_layout(self, layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget:
                widget.deleteLater()
            elif child_layout:
                self._clear_layout(child_layout)

    def _clear_cache(self) -> None:
        count = self.cache.clear()
        QMessageBox.information(self, "缓存", f"已清理 {count} 个缓存文件。")
        self.refresh()

    def _switch_to_keys(self) -> None:
        QMessageBox.information(self, "免费 API key", "请打开“API key”页签配置对应 provider。")

    def _clear(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
