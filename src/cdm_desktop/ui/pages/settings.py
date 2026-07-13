from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop import APP_MODE_LABEL, PRODUCT_NAME_ZH, __version__
from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.cache import ApiCache
from cdm_desktop.public_api.crawl_cache import WebEvidenceCache
from cdm_desktop.public_api.crawlergo_provider import CrawlergoWebEvidenceProvider
from cdm_desktop.public_api.key_store import ApiKeyStore
from cdm_desktop.public_api.models import ProviderStatus
from cdm_desktop.public_api.registry import ProviderRegistry
from cdm_desktop.public_api.search_service import PublicSearchService
from cdm_desktop.public_api.settings_store import PublicApiSettingsStore
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
from cdm_desktop.ui.theme import ThemeManager
from cdm_desktop.ui.widgets import ProgressFunctionWorker

ADVANCED_API_PROVIDERS = {"fmp", "alpha_vantage", "marketaux", "opencorporates", "companies_house"}


class SettingsPage(QWidget):
    route = "/settings"
    page_title = "设置"

    def __init__(self, navigate: Callable[[str], None], paths: AppPaths | None = None) -> None:
        super().__init__()
        self.navigate = navigate
        self.paths = paths
        self.key_store = ApiKeyStore(paths)
        self.registry = ProviderRegistry()
        self.search_service = PublicSearchService(paths)
        self.settings_store = PublicApiSettingsStore(paths)
        self.cache = ApiCache(paths)
        self.web_evidence_cache = WebEvidenceCache(paths)
        self.inputs: dict[str, QLineEdit] = {}
        self.thread_pool = QThreadPool.globalInstance()
        self.test_running = False
        self.last_test_statuses: list[ProviderStatus] = []
        self.theme_buttons: dict[str, QRadioButton] = {}
        manager = ThemeManager.instance()
        if manager:
            manager.theme_changed.connect(self._sync_theme_buttons)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _content, self.layout = scroll_container()
        root.addWidget(scroll)
        self.refresh()

    def refresh(self) -> None:
        self._clear()
        self.layout.addWidget(
            PageHeader(
                "设置",
                "管理外观、数据来源、搜索、缓存和隐私。",
                primary_text="保存设置",
                primary_action=self._save_settings,
            )
        )
        self.layout.addWidget(self._test_progress_panel())

        tabs = QTabWidget()
        tabs.addTab(self._appearance_tab(), "外观")
        tabs.addTab(self._overview_tab(), "数据源")
        tabs.addTab(self._public_sources_tab(), "公开数据源")
        tabs.addTab(self._search_settings_tab(), "搜索")
        tabs.addTab(self._cache_privacy_tab(), "缓存与隐私")
        tabs.addTab(self._keys_tab(), "高级数据源")
        tabs.addTab(self._crawlergo_tab(), "高级")
        tabs.addTab(self._about_tab(), "关于")
        self.layout.addWidget(tabs)
        self.layout.addStretch()

    def _appearance_tab(self) -> QWidget:
        page = self._tab_page()
        panel, panel_layout = self._compact_panel("主题", "主题切换立即生效，无需重启软件。")
        manager = ThemeManager.instance()
        current = manager.preference if manager else "system"
        group = QButtonGroup(panel)
        self.theme_buttons = {}
        row = QHBoxLayout()
        for label, value in [("跟随系统", "system"), ("浅色", "light"), ("深色", "dark")]:
            button = QRadioButton(label)
            button.setChecked(current == value)
            button.toggled.connect(
                lambda checked, preference=value: manager.apply(preference) if checked and manager else None
            )
            group.addButton(button)
            self.theme_buttons[value] = button
            row.addWidget(button)
        row.addStretch()
        panel_layout.addLayout(row)
        note = QLabel("界面采用高对比度文字、统一绿色强调色和紧凑列表，不使用伪造行情或图表。")
        note.setObjectName("MutedText")
        note.setWordWrap(True)
        panel_layout.addWidget(note)
        page.layout().addWidget(panel)
        return page

    def _sync_theme_buttons(self, _resolved: str) -> None:
        manager = ThemeManager.instance()
        if not manager:
            return
        for preference, button in self.theme_buttons.items():
            button.blockSignals(True)
            button.setChecked(preference == manager.preference)
            button.blockSignals(False)

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
                    ("高级 API key", f"{configured_keys} / {len(self.registry.key_definitions())}", "默认不需要"),
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
            "高级 API 数据源",
            "普通用户默认无需配置。只有高级用户需要扩展覆盖时，才启用并填写第三方 API key。",
        )
        enabled = self.settings_store.advanced_api_providers_enabled()
        enable_box = QCheckBox("启用高级 API 数据源")
        enable_box.setChecked(enabled)
        enable_box.stateChanged.connect(lambda _state: self.settings_store.set_advanced_api_providers_enabled(enable_box.isChecked()))
        intro_layout.addWidget(StatusBadge("默认关闭", "neutral" if not enabled else "warning"))
        intro_layout.addWidget(enable_box)
        page.layout().addWidget(intro)

        recommended, recommended_layout = self._compact_panel("兼容与高级 API 数据源")
        optional, optional_layout = self._compact_panel("其他可选 API Providers")
        for definition in self.registry.key_definitions():
            row = self._key_row(
                definition.provider_id,
                definition.key_name,
                definition.label,
                definition.registration_url,
                definition.help_text,
            )
            target = recommended_layout if definition.provider_id in ADVANCED_API_PROVIDERS else optional_layout
            target.addWidget(row)
        page.layout().addWidget(recommended)
        page.layout().addWidget(optional)
        return page

    def _public_sources_tab(self) -> QWidget:
        page = self._tab_page()
        panel, panel_layout = self._compact_panel(
            "无 key 公开来源",
            "这些来源无需普通用户申请 API key，但仍可能受网络、依赖、限流或字段覆盖影响。",
        )
        status_map = {status.provider_id: status for status in self.search_service.provider_statuses()}
        for provider in [item for item in self.registry.all() if not item.requires_key and item.enabled_by_default]:
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

    def _crawlergo_tab(self) -> QWidget:
        page = self._tab_page()
        policy = self.settings_store.crawlergo_policy()
        provider = CrawlergoWebEvidenceProvider(crawlergo_path=self.settings_store.crawlergo_path(), cache=self.web_evidence_cache)
        state, message = provider.dependency_status()

        intro, intro_layout = self._compact_panel(
            "网页证据采集",
            "仅用于用户指定公司官网或授权公开页面。软件不会绕过登录、验证码、登录凭据、访问令牌或 robots.txt 限制。",
        )
        intro_layout.addWidget(StatusBadge(friendly_state_label(state), friendly_state_tone(state)))
        note = QLabel("默认只展示短摘录、元数据和原文链接；雪球仅外部打开，不缓存第三方网页全文，不进入 AI/RAG。")
        note.setObjectName("MutedText")
        note.setWordWrap(True)
        intro_layout.addWidget(note)
        page.layout().addWidget(intro)

        config, config_layout = self._compact_panel("crawlergo 配置", message)
        path_row = QHBoxLayout()
        self.crawlergo_path_input = QLineEdit()
        self.crawlergo_path_input.setPlaceholderText("crawlergo.exe 路径，例如 C:\\tools\\crawlergo\\crawlergo.exe")
        self.crawlergo_path_input.setText(self.settings_store.crawlergo_path())
        browse_btn = QPushButton("选择")
        browse_btn.clicked.connect(self._choose_crawlergo_path)
        test_btn = QPushButton("测试 crawlergo")
        test_btn.clicked.connect(self._test_crawlergo)
        path_row.addWidget(QLabel("二进制路径"))
        path_row.addWidget(self.crawlergo_path_input, 1)
        path_row.addWidget(browse_btn)
        path_row.addWidget(test_btn)
        config_layout.addLayout(path_row)

        limits = QGridLayout()
        self.crawlergo_max_pages = QSpinBox()
        self.crawlergo_max_pages.setRange(1, 50)
        self.crawlergo_max_pages.setValue(policy.max_pages_per_domain)
        self.crawlergo_max_depth = QSpinBox()
        self.crawlergo_max_depth.setRange(0, 3)
        self.crawlergo_max_depth.setValue(policy.max_depth)
        self.crawlergo_delay = QSpinBox()
        self.crawlergo_delay.setRange(1, 30)
        self.crawlergo_delay.setValue(int(policy.request_delay_seconds))
        self.crawlergo_delay.setSuffix(" 秒")
        self.crawlergo_timeout = QSpinBox()
        self.crawlergo_timeout.setRange(5, 120)
        self.crawlergo_timeout.setValue(policy.timeout_seconds)
        self.crawlergo_timeout.setSuffix(" 秒")
        self.crawlergo_cache_ttl = QSpinBox()
        self.crawlergo_cache_ttl.setRange(1, 168)
        self.crawlergo_cache_ttl.setValue(max(1, int(policy.cache_ttl_seconds / 3600)))
        self.crawlergo_cache_ttl.setSuffix(" 小时")
        self.crawlergo_full_text = QCheckBox("高级模式：允许展示完整提取文本")
        self.crawlergo_full_text.setChecked(policy.allow_full_text_display)
        limits.addWidget(QLabel("最大页数"), 0, 0)
        limits.addWidget(self.crawlergo_max_pages, 0, 1)
        limits.addWidget(QLabel("最大深度"), 0, 2)
        limits.addWidget(self.crawlergo_max_depth, 0, 3)
        limits.addWidget(QLabel("请求间隔"), 1, 0)
        limits.addWidget(self.crawlergo_delay, 1, 1)
        limits.addWidget(QLabel("超时"), 1, 2)
        limits.addWidget(self.crawlergo_timeout, 1, 3)
        limits.addWidget(QLabel("缓存 TTL"), 2, 0)
        limits.addWidget(self.crawlergo_cache_ttl, 2, 1)
        limits.addWidget(StatusBadge("robots.txt 始终开启", "success"), 2, 2)
        limits.addWidget(self.crawlergo_full_text, 2, 3)
        config_layout.addLayout(limits)
        page.layout().addWidget(config)

        boundaries, boundaries_layout = self._compact_panel("合规边界")
        boundaries_layout.addWidget(
            DetailGrid(
                [
                    ("允许入口", "公司详情页手动点击、用户手动输入 URL、确认后的公司官网"),
                    ("默认页数 / 深度", f"{policy.max_pages_per_domain} 页 / 深度 {policy.max_depth}"),
                    ("robots.txt", "采集前检查；不允许则跳过"),
                    ("禁止内容", "登录页、验证码、付费墙、社交平台正文、雪球内容"),
                    ("缓存内容", "metadata、snippet、URL hash、抓取时间；不保存完整 HTML"),
                    ("网页证据缓存大小", f"{self.web_evidence_cache.size_bytes() / 1024:.1f} KB"),
                ],
                columns=2,
            )
        )
        page.layout().addWidget(boundaries)
        return page

    def _cache_privacy_tab(self) -> QWidget:
        page = self._tab_page()
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        cache_panel, cache_layout = self._compact_panel("本地缓存", "用于减少公开数据源请求次数，不会打包进安装包。")
        total_cache = self.cache.size_bytes() + self.web_evidence_cache.size_bytes()
        cache_layout.addWidget(QLabel(f"当前缓存大小：{total_cache / 1024:.1f} KB"))
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
            ("质量标记", "v0.1.3 Modern Financial UI"),
            ("真实业务边界", "不提供投资建议，不提供交易、买卖、下单、目标价或收益预测。"),
        ]
        if self.paths:
            fields.append(("本地数据目录", str(self.paths.app_data_dir)))
        panel_layout.addWidget(DetailGrid(fields, columns=2))
        page.layout().addWidget(panel)
        return page

    def _key_row(
        self,
        _provider_id: str,
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

        edit = QLineEdit()
        edit.setEchoMode(QLineEdit.EchoMode.Password)
        edit.setPlaceholderText(f"当前：{masked}" if configured else "高级用户可粘贴 API key / API 凭证 / GUID")
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
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        return page

    def _save_settings(self) -> None:
        self._save_crawlergo_settings(show_message=False)
        self._save_keys()

    def _save_keys(self) -> None:
        saved = 0
        for key_name, edit in self.inputs.items():
            value = edit.text().strip()
            if value:
                self.key_store.set(key_name, value)
                saved += 1
        QMessageBox.information(self, "设置", f"已保存 {saved} 个本机 key 和网页证据采集设置。普通搜索默认不需要 API key。")
        self.refresh()

    def _save_crawlergo_settings(self, *, show_message: bool = True) -> None:
        if hasattr(self, "crawlergo_path_input"):
            self.settings_store.set_crawlergo_path(self.crawlergo_path_input.text())
        if hasattr(self, "crawlergo_max_pages"):
            policy = self.settings_store.crawlergo_policy()
            policy.max_pages_per_domain = self.crawlergo_max_pages.value()
            policy.max_depth = self.crawlergo_max_depth.value()
            policy.request_delay_seconds = float(self.crawlergo_delay.value())
            policy.timeout_seconds = self.crawlergo_timeout.value()
            policy.cache_ttl_seconds = self.crawlergo_cache_ttl.value() * 3600
            policy.allow_full_text_display = self.crawlergo_full_text.isChecked()
            self.settings_store.set_crawlergo_policy(policy)
        if show_message:
            QMessageBox.information(self, "网页证据采集", "crawlergo 设置已保存。")

    def _choose_crawlergo_path(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "选择 crawlergo.exe", "", "Executable (*.exe);;All files (*.*)")
        if path:
            self.crawlergo_path_input.setText(path)

    def _test_crawlergo(self) -> None:
        self._save_crawlergo_settings(show_message=False)
        provider = CrawlergoWebEvidenceProvider(crawlergo_path=self.settings_store.crawlergo_path(), cache=self.web_evidence_cache)
        state, message = provider.dependency_status()
        QMessageBox.information(self, "测试 crawlergo", f"{friendly_state_label(state)}：{message}")

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
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
            elif child_layout:
                self._clear_layout(child_layout)

    def _clear_cache(self) -> None:
        count = self.cache.clear() + self.web_evidence_cache.clear()
        QMessageBox.information(self, "缓存", f"已清理 {count} 个缓存文件。")
        self.refresh()

    def _switch_to_keys(self) -> None:
        QMessageBox.information(self, "高级 API 数据源", "普通用户无需配置；如需扩展覆盖，请打开“高级数据源”页签。")

    def _clear(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
