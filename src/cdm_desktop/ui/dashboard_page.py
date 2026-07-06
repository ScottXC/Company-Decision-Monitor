from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from cdm_desktop.db import DatabaseManager
from cdm_desktop.db.repositories import AlertRepository, EventRepository
from cdm_desktop.paths import AppPaths
from cdm_desktop.services.hot_company_service import HotCompanyCandidate, HotCompanyService
from cdm_desktop.services.recycle_bin_service import RecycleBinService
from cdm_desktop.services.ui_query_service import get_alert_cards, get_event_cards, get_home_summary
from cdm_desktop.services.watchlist_service import WatchlistService
from cdm_desktop.ui.company_detail_dialog import CompanyDetailDialog
from cdm_desktop.ui.event_detail_dialog import EventDetailDialog
from cdm_desktop.ui.widgets import (
    AlertCard,
    EmptyState,
    EventCard,
    EvidenceDialog,
    HotCompanyCard,
    MetricCard,
    clear_layout,
    info,
    make_scroll_area,
    warn,
)


class DashboardPage(QWidget):
    page_title = "首页"
    primary_action_text = "搜索添加公司"

    def __init__(
        self,
        db: DatabaseManager,
        paths: AppPaths,
        open_company_callback: Callable[[int], None] | None = None,
        open_online_search_callback: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self.db = db
        self.paths = paths
        self.open_company_callback = open_company_callback
        self.open_online_search_callback = open_online_search_callback

        root = QVBoxLayout(self)
        self.scroll, _content, self.content_layout = make_scroll_area()
        root.addWidget(self.scroll, 1)

        hero = QHBoxLayout()
        title_block = QVBoxLayout()
        title = QLabel("今天需要关注什么？")
        title.setObjectName("HeroTitle")
        subtitle = QLabel("先把公司加入自选，再集中查看事件、告警、证据和监控状态。")
        subtitle.setObjectName("MutedText")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        hero.addLayout(title_block)
        hero.addStretch()
        self.content_layout.addLayout(hero)

        self.onboarding_container = QVBoxLayout()
        self.content_layout.addLayout(self.onboarding_container)

        metrics = QGridLayout()
        self.company_metric = MetricCard("自选公司")
        self.unread_metric = MetricCard("未读告警")
        self.high_metric = MetricCard("高优先级告警")
        self.today_metric = MetricCard("今日新增事件")
        self.source_metric = MetricCard("数据源状态")
        for idx, card in enumerate(
            [self.company_metric, self.unread_metric, self.high_metric, self.today_metric, self.source_metric]
        ):
            metrics.addWidget(card, 0, idx)
        self.content_layout.addLayout(metrics)

        self.content_layout.addWidget(_section_title("快速入口"))
        self.content_layout.addWidget(
            EmptyState(
                "通过公开来源添加公司",
                "进入联网搜索，使用 SEC、Nasdaq Trader、HKEX、Stock Connect 等无 API key 公开来源查找公司。",
                "打开联网搜索",
                self.focus_company_search,
            )
        )

        self.content_layout.addWidget(_section_title("网络热门公司"))
        disclaimer = QLabel("热门公司仅表示近期信息热度较高，不构成投资建议。")
        disclaimer.setObjectName("MutedText")
        self.content_layout.addWidget(disclaimer)
        self.hot_layout = QGridLayout()
        self.hot_layout.setHorizontalSpacing(10)
        self.hot_layout.setVerticalSpacing(10)
        self.content_layout.addLayout(self.hot_layout)

        columns = QHBoxLayout()
        left = QVBoxLayout()
        right = QVBoxLayout()
        left.addWidget(_section_title("重点告警"))
        self.alerts_layout = QVBoxLayout()
        left.addLayout(self.alerts_layout)
        right.addWidget(_section_title("最新动态"))
        self.events_layout = QVBoxLayout()
        right.addLayout(self.events_layout)
        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        self.content_layout.addLayout(columns, 1)
        self.refresh()

    def run_primary_action(self) -> None:
        self.focus_company_search()

    def refresh(self) -> None:
        for layout in [self.onboarding_container, self.alerts_layout, self.events_layout]:
            clear_layout(layout)
        clear_layout(self.hot_layout)

        with self.db.session() as session:
            summary = get_home_summary(session)
            alert_cards = get_alert_cards(session, inbox_filter="unread", limit=10)
            event_cards = get_event_cards(session, limit=8)
            hot_companies = HotCompanyService(session).get_hot_companies(limit=8)

        self.company_metric.set_value(summary.companies)
        self.unread_metric.set_value(summary.unread_alerts)
        self.high_metric.set_value(summary.high_priority_alerts)
        self.today_metric.set_value(summary.today_events)
        self.source_metric.set_value(f"{summary.sources_enabled}/{summary.sources_total}", "启用 / 总数")

        if summary.companies == 0:
            self.onboarding_container.addWidget(
                EmptyState(
                    "先添加你要监控的公司",
                    "进入联网搜索，从公开来源选择公司加入自选后，即可集中查看事件、告警、证据、文档和监控状态。",
                    "打开联网搜索",
                    self.focus_company_search,
                    "联网搜索公司",
                    self.focus_company_search,
                )
            )

        if not hot_companies:
            self.hot_layout.addWidget(
                EmptyState(
                    "暂无热门公司",
                    "联网搜索或采集真实数据后，会根据事件、告警和文档提及生成热度列表。",
                ),
                0,
                0,
            )
        for index, candidate in enumerate(hot_companies):
            self.hot_layout.addWidget(
                HotCompanyCard(
                    candidate,
                    on_add=self.add_hot_company,
                    on_view=self.view_hot_company,
                ),
                index // 4,
                index % 4,
            )

        top_alerts = [card for card in alert_cards if card.priority in {"P0", "P1", "P2"}][:3]
        if not top_alerts:
            self.alerts_layout.addWidget(EmptyState("暂无需要处理的告警", "新告警会出现在这里。"))
        for card in top_alerts:
            self.alerts_layout.addWidget(self._alert_card(card))

        if not event_cards:
            self.events_layout.addWidget(EmptyState("暂无重大事件", "采集并解析公开资料后，事件会以动态流展示。"))
        for card in event_cards:
            self.events_layout.addWidget(self._event_card(card))
        self.alerts_layout.addStretch()
        self.events_layout.addStretch()

    def focus_company_search(self) -> None:
        if self.open_online_search_callback:
            self.open_online_search_callback("")

    def add_hot_company(self, candidate: HotCompanyCandidate) -> None:
        with self.db.session() as session:
            search_candidate = HotCompanyService.to_search_candidate(candidate)
            result = WatchlistService(session).add_to_watchlist(search_candidate)
            company_id = result.company_id
        self.refresh()
        info(self, "已加入自选")
        self.open_company(company_id)

    def view_hot_company(self, candidate: HotCompanyCandidate) -> None:
        if candidate.company_id:
            self.open_company(candidate.company_id)
            return
        if self.open_online_search_callback:
            self.open_online_search_callback(candidate.name)

    def _alert_card(self, card) -> AlertCard:
        return AlertCard(
            company_name=card.company_name,
            priority=card.priority,
            title=card.title,
            message=card.message,
            status=card.status,
            confidence_score=card.confidence_score,
            materiality_score=card.materiality_score,
            created_text=card.created_at.strftime("%m-%d %H:%M"),
            evidence=card.evidence,
            on_evidence=lambda event_id=card.event_id: self.open_evidence(event_id),
            on_ack=lambda alert_id=card.id: self.set_alert_status(alert_id, "acknowledged"),
            on_ignore=lambda alert_id=card.id: self.set_alert_status(alert_id, "ignored"),
            on_company=lambda company_id=card.company_id: self.open_company(company_id),
            on_delete=lambda alert_id=card.id: self.delete_alert(alert_id),
        )

    def _event_card(self, card) -> EventCard:
        return EventCard(
            company_name=card.company_name,
            priority=card.priority,
            title=card.title,
            event_type=card.event_type,
            event_status=card.event_status,
            confidence_score=card.confidence_score,
            materiality_score=card.materiality_score,
            source_label=card.source_label,
            created_text=card.created_at.strftime("%m-%d %H:%M"),
            evidence=card.evidence,
            on_evidence=lambda event_id=card.id: self.open_evidence(event_id),
            on_company=lambda company_id=card.company_id: self.open_company(company_id),
            on_detail=lambda event_id=card.id: EventDetailDialog(self.db, event_id, self).exec(),
            on_ack=(lambda alert_id=card.alert_id: self.set_alert_status(alert_id, "acknowledged")) if card.alert_id else None,
            on_delete=lambda event_id=card.id: self.delete_event(event_id),
        )

    def set_alert_status(self, alert_id: int | None, status: str) -> None:
        if alert_id is None:
            return
        with self.db.session() as session:
            AlertRepository(session).set_status(alert_id, status)
        self.refresh()

    def delete_event(self, event_id: int) -> None:
        try:
            with self.db.session() as session:
                RecycleBinService(session).move_event_to_recycle(event_id)
        except Exception as exc:
            warn(self, f"删除失败：{exc}")
            return
        self.refresh()
        info(self, "事件已移入回收站")

    def delete_alert(self, alert_id: int) -> None:
        try:
            with self.db.session() as session:
                RecycleBinService(session).move_alert_to_recycle(alert_id)
        except Exception as exc:
            warn(self, f"删除失败：{exc}")
            return
        self.refresh()
        info(self, "告警已移入回收站")

    def open_evidence(self, event_id: int) -> None:
        with self.db.session() as session:
            evidence = EventRepository(session).evidence_for_event(event_id)
        EvidenceDialog("证据", [item.snippet for item in evidence], self).exec()

    def open_company(self, company_id: int) -> None:
        if self.open_company_callback:
            self.open_company_callback(company_id)
        else:
            CompanyDetailDialog(self.db, self.paths, company_id, self).exec()
            self.refresh()


def _section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    label.setAlignment(Qt.AlignmentFlag.AlignLeft)
    return label
