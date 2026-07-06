from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import delete

from cdm_desktop import PRODUCT_NAME_ZH, __version__
from cdm_desktop.db import DatabaseManager
from cdm_desktop.db.models import OnlineProviderCache, OnlineSearchResult, RecentSearch
from cdm_desktop.db.repositories import SettingsRepository, SourceRepository
from cdm_desktop.paths import AppPaths
from cdm_desktop.search.online_search_service import OnlineCompanySearchService
from cdm_desktop.services.reset_service import reset_user_data
from cdm_desktop.services.scheduler_service import SchedulerService
from cdm_desktop.ui.recycle_bin_page import RecycleBinPage
from cdm_desktop.ui.sources_page import SourcesPage
from cdm_desktop.ui.widgets import info, set_table_rows, warn


class SettingsPage(QWidget):
    page_title = "设置"
    primary_action_text = "保存设置"

    def __init__(
        self,
        db: DatabaseManager,
        paths: AppPaths,
        scheduler: SchedulerService,
        refresh_callback: Callable[[], None],
    ) -> None:
        super().__init__()
        self.db = db
        self.paths = paths
        self.scheduler = scheduler
        self.refresh_callback = refresh_callback
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_online_search_tab(), "联网搜索")
        self.tabs.addTab(SourcesPage(db, paths, refresh_callback), "数据源管理")
        self.tabs.addTab(self._build_monitoring_tab(), "自动监控")
        self.tabs.addTab(self._build_threshold_tab(), "告警阈值")
        self.tabs.addTab(RecycleBinPage(db, refresh_callback), "回收站")
        self.tabs.addTab(self._build_local_data_tab(), "本地数据")
        self.tabs.addTab(self._build_diagnostics_tab(), "高级诊断")
        self.tabs.addTab(self._build_about_tab(), "关于")
        layout.addWidget(self.tabs, 1)
        self.refresh()

    def run_primary_action(self) -> None:
        self.save()

    def _build_monitoring_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.monitoring_enabled = QCheckBox()
        self.run_on_startup = QCheckBox()
        self.interval = QSpinBox()
        self.interval.setRange(1, 1440)
        self.max_fetch = QSpinBox()
        self.max_fetch.setRange(10_000, 50_000_000)
        self.max_fetch.setSingleStep(100_000)
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 120)
        form.addRow("启用自动监控", self.monitoring_enabled)
        form.addRow("启动时运行", self.run_on_startup)
        form.addRow("监测间隔（分钟）", self.interval)
        form.addRow("最大抓取字节数", self.max_fetch)
        form.addRow("HTTP 超时（秒）", self.timeout)
        layout.addLayout(form)
        save_btn = QPushButton("保存设置")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self.save)
        layout.addWidget(save_btn)
        layout.addStretch()
        return page

    def _build_online_search_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.online_search_enabled = QCheckBox()
        self.online_sec_enabled = QCheckBox()
        self.online_nasdaq_enabled = QCheckBox()
        self.online_hkex_enabled = QCheckBox()
        self.online_stock_connect_enabled = QCheckBox()
        self.online_hkexnews_enabled = QCheckBox()
        self.online_rss_enabled = QCheckBox()
        self.online_ir_enabled = QCheckBox()
        self.online_sec_user_agent = QLineEdit()
        self.online_cache_hours = QSpinBox()
        self.online_cache_hours.setRange(1, 720)
        self.online_timeout = QSpinBox()
        self.online_timeout.setRange(3, 120)
        self.online_max_results = QSpinBox()
        self.online_max_results.setRange(5, 100)
        for label, widget in [
            ("启用联网搜索", self.online_search_enabled),
            ("SEC 搜索", self.online_sec_enabled),
            ("Nasdaq Trader 搜索", self.online_nasdaq_enabled),
            ("HKEX 证券列表搜索", self.online_hkex_enabled),
            ("Stock Connect A股搜索", self.online_stock_connect_enabled),
            ("HKEXnews 搜索", self.online_hkexnews_enabled),
            ("RSS 新闻搜索", self.online_rss_enabled),
            ("用户配置 IR 页面搜索", self.online_ir_enabled),
            ("SEC User-Agent 联系邮箱", self.online_sec_user_agent),
            ("缓存有效期（小时）", self.online_cache_hours),
            ("请求超时（秒）", self.online_timeout),
            ("最大结果数", self.online_max_results),
        ]:
            form.addRow(label, widget)
        layout.addLayout(form)
        note = QLabel("核心联网搜索使用公开文件、公开网页和 RSS，不需要 API key。SEC 建议 User-Agent 包含联系邮箱。")
        note.setObjectName("MutedText")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QHBoxLayout()
        clear_btn = QPushButton("清空联网搜索缓存")
        clear_btn.clicked.connect(self.clear_online_cache)
        refresh_btn = QPushButton("刷新公开公司列表")
        refresh_btn.clicked.connect(self.refresh_online_reference_data)
        buttons.addWidget(clear_btn)
        buttons.addWidget(refresh_btn)
        buttons.addStretch()
        layout.addLayout(buttons)
        layout.addStretch()
        return page

    def _build_threshold_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.p0_materiality = _score_spin()
        self.p0_confidence = _score_spin()
        self.p1_materiality = _score_spin()
        self.p1_confidence = _score_spin()
        self.p2_materiality = _score_spin()
        self.p2_confidence = _score_spin()
        for label, widget in [
            ("P0 重大性阈值", self.p0_materiality),
            ("P0 置信度阈值", self.p0_confidence),
            ("P1 重大性阈值", self.p1_materiality),
            ("P1 置信度阈值", self.p1_confidence),
            ("P2 重大性阈值", self.p2_materiality),
            ("P2 置信度阈值", self.p2_confidence),
        ]:
            form.addRow(label, widget)
        layout.addLayout(form)
        note = QLabel("阈值用于界面展示和后续规则配置。当前 v1 事件告警仍使用内置稳定规则。")
        note.setObjectName("MutedText")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        return page

    def _build_local_data_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        form.addRow("AppData 目录", QLabel(str(self.paths.app_data_dir)))
        form.addRow("数据库路径", QLabel(str(self.paths.db_path)))
        form.addRow("原始文档目录", QLabel(str(self.paths.raw_documents_dir)))
        form.addRow("导出目录", QLabel(str(self.paths.exports_dir)))
        form.addRow("缓存目录", QLabel(str(self.paths.cache_dir)))
        layout.addLayout(form)
        buttons = QHBoxLayout()
        for text, path in [
            ("打开数据目录", self.paths.app_data_dir),
            ("打开导出目录", self.paths.exports_dir),
        ]:
            button = QPushButton(text)
            button.clicked.connect(lambda _checked=False, p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p))))
            buttons.addWidget(button)
        reset_btn = QPushButton("清空所有本地数据")
        reset_btn.setObjectName("DangerButton")
        reset_btn.clicked.connect(self.reset_all_local_data)
        buttons.addWidget(reset_btn)
        buttons.addStretch()
        layout.addLayout(buttons)
        layout.addStretch()
        return page

    def _build_diagnostics_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("最近数据源运行"))
        self.runs_table = QTableWidget()
        layout.addWidget(self.runs_table)
        layout.addWidget(QLabel("最近错误"))
        self.errors_table = QTableWidget()
        layout.addWidget(self.errors_table)
        self.log_path_label = QLabel(str(self.paths.logs_dir / "cdm.log"))
        self.log_path_label.setObjectName("MutedText")
        layout.addWidget(self.log_path_label)
        return page

    def _build_about_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel(PRODUCT_NAME_ZH)
        title.setObjectName("DetailHeader")
        layout.addWidget(title)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(
            f"版本：{__version__}\n\n"
            "本软件仅用于信息监测和研究，不提供投资建议。\n"
            "所有数据保存在本机 SQLite 数据库中，不需要云账号或服务器。"
        )
        layout.addWidget(text)
        return page

    def refresh(self) -> None:
        with self.db.session() as session:
            settings = SettingsRepository(session)
            self.monitoring_enabled.setChecked(settings.get("monitoring_enabled", "false") == "true")
            self.run_on_startup.setChecked(settings.get("run_on_startup", "false") == "true")
            self.interval.setValue(int(settings.get("monitoring_interval_minutes", "60") or "60"))
            self.max_fetch.setValue(int(settings.get("max_fetch_bytes", "5000000") or "5000000"))
            self.timeout.setValue(int(settings.get("http_timeout_seconds", "15") or "15"))
            self.p0_materiality.setValue(int(settings.get("p0_materiality", "90") or "90"))
            self.p0_confidence.setValue(int(settings.get("p0_confidence", "85") or "85"))
            self.p1_materiality.setValue(int(settings.get("p1_materiality", "75") or "75"))
            self.p1_confidence.setValue(int(settings.get("p1_confidence", "75") or "75"))
            self.p2_materiality.setValue(int(settings.get("p2_materiality", "55") or "55"))
            self.p2_confidence.setValue(int(settings.get("p2_confidence", "60") or "60"))
            self.online_search_enabled.setChecked(settings.get("online_search_enabled", "true") == "true")
            self.online_sec_enabled.setChecked(settings.get("online_search_sec_enabled", "true") == "true")
            self.online_nasdaq_enabled.setChecked(settings.get("online_search_nasdaq_enabled", "true") == "true")
            self.online_hkex_enabled.setChecked(settings.get("online_search_hkex_enabled", "true") == "true")
            self.online_stock_connect_enabled.setChecked(settings.get("online_search_stock_connect_enabled", "true") == "true")
            self.online_hkexnews_enabled.setChecked(settings.get("online_search_hkexnews_enabled", "false") == "true")
            self.online_rss_enabled.setChecked(settings.get("online_search_rss_enabled", "true") == "true")
            self.online_ir_enabled.setChecked(settings.get("online_search_ir_enabled", "true") == "true")
            self.online_sec_user_agent.setText(settings.get("online_search_sec_user_agent", "CompanyDecisionMonitor contact@example.com") or "")
            self.online_cache_hours.setValue(int(settings.get("online_search_cache_hours", "24") or "24"))
            self.online_timeout.setValue(int(settings.get("online_search_timeout_seconds", "15") or "15"))
            self.online_max_results.setValue(int(settings.get("online_search_max_results", "20") or "20"))

            runs = SourceRepository(session).latest_runs(50)
            set_table_rows(
                self.runs_table,
                ["ID", "源ID", "状态", "发现", "新增", "错误", "开始", "结束"],
                [
                    [
                        run.id,
                        run.source_id,
                        run.status,
                        run.documents_found,
                        run.documents_created,
                        run.error_message or "",
                        run.started_at.strftime("%Y-%m-%d %H:%M:%S"),
                        run.finished_at.strftime("%Y-%m-%d %H:%M:%S") if run.finished_at else "",
                    ]
                    for run in runs
                ],
                [run.id for run in runs],
            )
            errors = [run for run in runs if run.status == "failed" or run.error_message]
            set_table_rows(
                self.errors_table,
                ["ID", "源ID", "错误", "时间"],
                [
                    [
                        run.id,
                        run.source_id,
                        run.error_message or run.status,
                        run.finished_at.strftime("%Y-%m-%d %H:%M:%S") if run.finished_at else "",
                    ]
                    for run in errors
                ],
                [run.id for run in errors],
            )

    def save(self) -> None:
        with self.db.session() as session:
            settings = SettingsRepository(session)
            settings.set("monitoring_enabled", "true" if self.monitoring_enabled.isChecked() else "false")
            settings.set("run_on_startup", "true" if self.run_on_startup.isChecked() else "false")
            settings.set("monitoring_interval_minutes", str(self.interval.value()))
            settings.set("max_fetch_bytes", str(self.max_fetch.value()))
            settings.set("http_timeout_seconds", str(self.timeout.value()))
            settings.set("p0_materiality", str(self.p0_materiality.value()))
            settings.set("p0_confidence", str(self.p0_confidence.value()))
            settings.set("p1_materiality", str(self.p1_materiality.value()))
            settings.set("p1_confidence", str(self.p1_confidence.value()))
            settings.set("p2_materiality", str(self.p2_materiality.value()))
            settings.set("p2_confidence", str(self.p2_confidence.value()))
            settings.set("online_search_enabled", "true" if self.online_search_enabled.isChecked() else "false")
            settings.set("online_search_sec_enabled", "true" if self.online_sec_enabled.isChecked() else "false")
            settings.set("online_search_nasdaq_enabled", "true" if self.online_nasdaq_enabled.isChecked() else "false")
            settings.set("online_search_hkex_enabled", "true" if self.online_hkex_enabled.isChecked() else "false")
            settings.set(
                "online_search_stock_connect_enabled",
                "true" if self.online_stock_connect_enabled.isChecked() else "false",
            )
            settings.set("online_search_hkexnews_enabled", "true" if self.online_hkexnews_enabled.isChecked() else "false")
            settings.set("online_search_rss_enabled", "true" if self.online_rss_enabled.isChecked() else "false")
            settings.set("online_search_ir_enabled", "true" if self.online_ir_enabled.isChecked() else "false")
            settings.set("online_search_sec_user_agent", self.online_sec_user_agent.text().strip())
            settings.set("online_search_cache_hours", str(self.online_cache_hours.value()))
            settings.set("online_search_timeout_seconds", str(self.online_timeout.value()))
            settings.set("online_search_max_results", str(self.online_max_results.value()))
        if self.monitoring_enabled.isChecked():
            self.scheduler.enable(self.interval.value())
        else:
            self.scheduler.disable()
        self.refresh_callback()
        info(self, "设置已保存")

    def clear_online_cache(self) -> None:
        with self.db.session() as session:
            session.execute(delete(OnlineProviderCache))
            session.execute(delete(OnlineSearchResult))
            session.execute(delete(RecentSearch))
        info(self, "联网搜索缓存已清空")

    def reset_all_local_data(self) -> None:
        first_answer = QMessageBox.warning(
            self,
            "清空所有本地数据",
            "这将删除本地数据库、搜索缓存、已下载文档、日志和导出文件。此操作不可撤销。\n\n"
            "不会删除源代码或已安装程序文件。是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if first_answer != QMessageBox.StandardButton.Yes:
            return
        typed, ok = QInputDialog.getText(
            self,
            "确认清空",
            "请输入 DELETE 以确认清空所有本地数据：",
        )
        if not ok:
            return
        if typed.strip() != "DELETE":
            warn(self, "确认文本不正确，未清空本地数据。")
            return
        try:
            self.scheduler.reset_runtime()
            result = reset_user_data(self.db, self.paths)
        except Exception as exc:
            warn(self, f"清空本地数据失败：{exc}")
            return
        self.refresh()
        self.refresh_callback()
        deleted = "\n".join(str(path) for path in result.deleted_paths) or "没有发现旧数据目录"
        info(self, f"本地数据已清空，并已创建空数据库。\n\n已处理目录：\n{deleted}")

    def refresh_online_reference_data(self) -> None:
        with self.db.session() as session:
            results = OnlineCompanySearchService(session).refresh_reference_data()
        info(self, f"刷新完成：{len(results)} 个公开来源已处理。")


def _score_spin() -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(0, 100)
    return spin
