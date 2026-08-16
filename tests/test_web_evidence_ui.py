from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QLabel, QPlainTextEdit, QPushButton

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.models import CompanyProfile, CompanyResult
from cdm_desktop.public_api.web_evidence_models import WebEvidenceItem
from cdm_desktop.ui.components import CollapsibleSection
from cdm_desktop.ui.pages.company_detail import CompanyDetailPage
from cdm_desktop.ui.pages.settings import SettingsPage


def make_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        raw_documents_dir=tmp_path / "raw_documents",
        exports_dir=tmp_path / "exports",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "cdm.db",
    ).ensure()


def test_web_evidence_tab_actions_dependency_state_and_independent_pool(qtbot, tmp_path: Path) -> None:
    page = CompanyDetailPage(lambda _route: None, make_paths(tmp_path))
    qtbot.addWidget(page)
    company = CompanyResult(
        name="Example",
        website="https://example.com/",
        provider="Local",
        provider_id="symbol_universe",
    )
    tab = page._web_info_tab(company)
    qtbot.addWidget(tab)

    buttons = {button.text() for button in tab.findChildren(QPushButton)}
    labels = " ".join(label.text() for label in tab.findChildren(QLabel))
    diagnostics = tab.findChildren(CollapsibleSection)
    assert {"采集官网", "添加 URL", "刷新", "取消任务", "清理证据"}.issubset(buttons)
    assert "crawlergo" in labels.casefold()
    assert "robots.txt 始终开启" in labels
    assert diagnostics and diagnostics[0].body.isHidden()
    assert page.crawl_thread_pool is not page.thread_pool
    assert page.crawl_thread_pool.maxThreadCount() == 2
    page.shutdown()


def test_evidence_card_has_list_view_open_and_delete_actions(qtbot, tmp_path: Path) -> None:
    page = CompanyDetailPage(lambda _route: None, make_paths(tmp_path))
    qtbot.addWidget(page)
    item = WebEvidenceItem(
        id="evidence:1",
        company_id="company:1",
        source_url="https://example.com/ir",
        final_url="https://example.com/ir",
        canonical_url="https://example.com/ir",
        domain="example.com",
        title="Investor Relations",
        content_snippet="Official public information.",
        display_mode="full_cleaned_text",
        is_official_domain=True,
    )
    card = page._web_evidence_card(item)
    qtbot.addWidget(card)

    buttons = {button.text() for button in card.findChildren(QPushButton)}
    labels = " ".join(label.text() for label in card.findChildren(QLabel))
    assert {"打开原文", "查看内容", "删除"}.issubset(buttons)
    assert "来自公开网页" in labels
    assert "full_cleaned_text" in labels
    page.shutdown()


def test_official_page_without_body_explains_javascript_limitation(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    page = CompanyDetailPage(lambda _route: None, make_paths(tmp_path))
    qtbot.addWidget(page)
    dialogs: list[QDialog] = []
    monkeypatch.setattr(QDialog, "exec", lambda dialog: dialogs.append(dialog))
    item = WebEvidenceItem(
        id="evidence:js-only",
        company_id="company:1",
        source_url="https://example.com/investors",
        final_url="https://example.com/investors",
        canonical_url="https://example.com/investors",
        domain="example.com",
        title="Investor Relations",
        display_mode="full_cleaned_text",
        is_official_domain=True,
    )

    page._view_web_evidence(item)

    assert dialogs
    viewer = dialogs[0].findChild(QPlainTextEdit)
    assert viewer is not None
    assert "页面主要依赖 JavaScript，当前未提取到可用正文。" in viewer.toPlainText()
    page.shutdown()


def test_settings_exposes_web_evidence_runtime_storage_and_limits(qtbot, tmp_path: Path) -> None:
    page = SettingsPage(lambda _route: None, make_paths(tmp_path))
    qtbot.addWidget(page)
    labels = " ".join(label.text() for label in page.findChildren(QLabel))
    buttons = {button.text() for button in page.findChildren(QPushButton)}

    assert "Crawlergo Runtime" in labels
    assert "AppData/web_evidence.sqlite" in labels
    assert "robots.txt 始终开启" in labels
    assert "清理全部网页证据缓存" in buttons


def test_profile_candidate_confirmation_controls_are_rendered(qtbot, tmp_path: Path) -> None:
    page = CompanyDetailPage(lambda _route: None, make_paths(tmp_path))
    qtbot.addWidget(page)
    company = CompanyResult(
        name="Example",
        website="https://example.com/",
        provider="Local",
        provider_id="symbol_universe",
    )
    tab = page._web_info_tab(company)
    qtbot.addWidget(tab)
    item = WebEvidenceItem(
        id="evidence:candidate",
        company_id=company.dedupe_key(),
        company_name=company.name,
        source_url="https://example.com/",
        final_url="https://example.com/",
        canonical_url="https://example.com/",
        domain="example.com",
        title="Example",
        is_official_domain=True,
    )
    page.web_evidence_store.save_evidence(item)
    from cdm_desktop.public_api.web_evidence_models import ProfileFieldCandidate

    candidate = ProfileFieldCandidate(
        field_name="legal_name",
        proposed_value="Example Corporation",
        source_url=item.canonical_url,
        evidence_id=item.id,
        confidence=0.98,
        current_value="Conflicting Name",
        status="pending",
    )
    page.web_evidence_store.save_candidate(company.dedupe_key(), candidate)
    page._render_profile_candidates([candidate])

    buttons = {button.text() for button in tab.findChildren(QPushButton)}
    assert "接受候选" in buttons
    assert "拒绝候选" in buttons
    page.shutdown()


def test_crawl_worker_keeps_the_profile_snapshot_from_start(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    page = CompanyDetailPage(lambda _route: None, make_paths(tmp_path))
    qtbot.addWidget(page)
    company = CompanyResult(
        name="Example",
        website="https://example.com/",
        provider="Local",
        provider_id="symbol_universe",
    )
    page.current_company = company
    tab = page._web_info_tab(company)
    qtbot.addWidget(tab)
    original_profile = CompanyProfile(legal_name="Example Corporation")
    page._loaded_profile = original_profile
    captured: list[object] = []
    monkeypatch.setattr(
        page,
        "_start_crawl_worker",
        lambda worker, _finished, _error: captured.append(worker),
    )

    page._start_web_evidence_crawl("https://example.com/")
    page._loaded_profile = CompanyProfile(legal_name="Other Corporation")

    assert captured
    worker = captured[0]
    assert worker.args[2] is original_profile  # type: ignore[attr-defined]
    page.web_crawl_cancel_event = None
    page.shutdown()
