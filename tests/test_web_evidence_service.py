from __future__ import annotations

import socket
import threading
from pathlib import Path

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.models import CompanyProfile
from cdm_desktop.public_api.robots_policy import RobotsDecision
from cdm_desktop.public_api.web_evidence_models import CrawlPolicy
from cdm_desktop.public_api.web_evidence_store import WebEvidenceStore
from cdm_desktop.public_api.web_fetcher import WebFetchResponse
from cdm_desktop.services.web_evidence_service import WebEvidenceService


def make_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        raw_documents_dir=tmp_path / "raw_documents",
        exports_dir=tmp_path / "exports",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "cdm.db",
    ).ensure()


def public_resolver(_host: str, _port: object, *, type: int = 0):
    _ = type
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


class AllowRobots:
    def can_fetch(self, url: str, **_kwargs) -> RobotsDecision:
        return RobotsDecision(True, f"{url.split('/', 3)[:3]}/robots.txt")


class BlockRobots:
    def can_fetch(self, _url: str, **_kwargs) -> RobotsDecision:
        return RobotsDecision(
            False,
            "https://example.com/robots.txt",
            error_message="该页面不允许自动采集（robots.txt 已禁止）。",
        )


class FakeFetcher:
    resolver = staticmethod(public_resolver)

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def fetch(self, url: str, **_kwargs):
        self.calls.append(url)
        html = self.pages.get(url, "<html><head><title>Missing</title></head><body>Missing</body></html>")
        return (
            WebFetchResponse(
                requested_url=url,
                final_url=url,
                content_type="text/html; charset=utf-8",
                content=html.encode(),
                text=html,
                status_code=200,
            ),
            None,
        )


OFFICIAL_HTML = """
<html lang="en"><head><title>Example Corp</title>
<meta name="description" content="Official company description">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Organization","name":"Example Corp",
"legalName":"Example Corporation","url":"https://example.com/"}
</script></head><body><main><h1>Example Corp</h1><p>Official public company information.</p>
<a href="/investors">Investors</a><a href="https://other.example/news">Other</a></main></body></html>
"""


def test_service_start_progress_store_candidates_and_same_domain_scope(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pages = {
        "https://example.com/": OFFICIAL_HTML,
        "https://example.com/investors": OFFICIAL_HTML.replace("Example Corp", "Investor Relations"),
    }
    fetcher = FakeFetcher(pages)
    store = WebEvidenceStore(make_paths(tmp_path))
    service = WebEvidenceService(
        fetcher=fetcher,  # type: ignore[arg-type]
        robots_policy=AllowRobots(),  # type: ignore[arg-type]
        store=store,
        resolver=public_resolver,
    )
    monkeypatch.setattr(
        "cdm_desktop.services.web_evidence_service._wait_for_domain_delay",
        lambda *_args, **_kwargs: True,
    )
    progress: list[tuple[int, int, str]] = []
    profile = CompanyProfile()

    result = service.crawl(
        company_id="company:1",
        company_name="Example",
        seed_urls=["https://example.com/"],
        company_website="https://example.com/",
        profile=profile,
        policy=CrawlPolicy(max_pages_per_domain=2, max_depth=1),
        progress_callback=lambda current, total, message: progress.append(
            (current, total, message)
        ),
    )

    assert result.job.status == "partial"
    assert result.job.pages_processed == 2
    assert len(result.items) == 2
    assert all(item.display_mode == "full_cleaned_text" for item in result.items)
    assert all(item.is_official_domain for item in result.items)
    assert len(store.list_evidence("company:1")) == 2
    assert result.profile_candidates
    assert profile.legal_name == "Example Corporation"
    assert progress
    assert all("other.example" not in call for call in fetcher.calls)
    assert any("默认仅采集同域名" in skip["reason"] for skip in result.skipped_urls)


def test_manual_third_party_url_uses_excerpt_only(tmp_path: Path) -> None:
    fetcher = FakeFetcher({"https://media.example/story": OFFICIAL_HTML})
    service = WebEvidenceService(
        fetcher=fetcher,  # type: ignore[arg-type]
        robots_policy=AllowRobots(),  # type: ignore[arg-type]
        store=WebEvidenceStore(make_paths(tmp_path)),
        resolver=public_resolver,
    )

    result = service.crawl(
        company_id="company:1",
        company_name="Example",
        seed_urls=["https://media.example/story"],
        company_website="https://example.com/",
        policy=CrawlPolicy(max_pages_per_domain=1, max_depth=0),
    )

    assert result.job.status == "success"
    assert result.items[0].display_mode == "excerpt_only"
    assert result.items[0].cleaned_text == ""
    assert result.items[0].content_snippet


def test_robots_blocked_is_recorded_without_fetch(tmp_path: Path) -> None:
    fetcher = FakeFetcher({})
    service = WebEvidenceService(
        fetcher=fetcher,  # type: ignore[arg-type]
        robots_policy=BlockRobots(),  # type: ignore[arg-type]
        store=WebEvidenceStore(make_paths(tmp_path)),
        resolver=public_resolver,
    )

    result = service.crawl(
        company_id="company:1",
        company_name="Example",
        seed_urls=["https://example.com/private"],
        policy=CrawlPolicy(max_pages_per_domain=1),
    )

    assert result.job.status == "blocked"
    assert result.job.pages_skipped == 1
    assert result.skipped_urls[0]["type"] == "robots_blocked"
    assert fetcher.calls == []


def test_cancel_before_start_and_shutdown_cancel_active_events(tmp_path: Path) -> None:
    service = WebEvidenceService(
        fetcher=FakeFetcher({}),  # type: ignore[arg-type]
        robots_policy=AllowRobots(),  # type: ignore[arg-type]
        store=WebEvidenceStore(make_paths(tmp_path)),
        resolver=public_resolver,
    )
    cancel = threading.Event()
    cancel.set()
    result = service.crawl(
        company_id="company:1",
        company_name="Example",
        seed_urls=["https://example.com/"],
        policy=CrawlPolicy(max_pages_per_domain=1),
        cancel_event=cancel,
    )
    assert result.job.status == "cancelled"
    assert result.job.cancelled

    active = threading.Event()
    service._active_cancel_events.add(active)
    service.shutdown()
    assert active.is_set()


def test_total_timeout_lifecycle_is_reported(tmp_path: Path, monkeypatch) -> None:
    service = WebEvidenceService(
        fetcher=FakeFetcher({}),  # type: ignore[arg-type]
        robots_policy=AllowRobots(),  # type: ignore[arg-type]
        store=WebEvidenceStore(make_paths(tmp_path)),
        resolver=public_resolver,
    )
    clock = iter([0.0, 10.0])
    monkeypatch.setattr(
        "cdm_desktop.services.web_evidence_service.time.monotonic",
        lambda: next(clock),
    )

    result = service.crawl(
        company_id="company:1",
        company_name="Example",
        seed_urls=["https://example.com/"],
        policy=CrawlPolicy(max_pages_per_domain=1, timeout_seconds=5),
    )

    assert result.job.status == "failed"
    assert result.job.error_type == "timeout"
    assert "总超时" in result.job.error_message


def test_xueqiu_is_rejected_before_robots_or_fetch(tmp_path: Path) -> None:
    fetcher = FakeFetcher({})
    service = WebEvidenceService(
        fetcher=fetcher,  # type: ignore[arg-type]
        robots_policy=AllowRobots(),  # type: ignore[arg-type]
        store=WebEvidenceStore(make_paths(tmp_path)),
        resolver=public_resolver,
    )
    result = service.crawl(
        company_id="company:1",
        company_name="Example",
        seed_urls=["https://xueqiu.com/S/AAPL"],
        policy=CrawlPolicy(max_pages_per_domain=1),
    )

    assert result.items == []
    assert result.skipped_urls
    assert fetcher.calls == []


def test_rejected_profile_candidate_is_not_reapplied_on_recrawl(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = WebEvidenceStore(make_paths(tmp_path))
    fetcher = FakeFetcher({"https://example.com/": OFFICIAL_HTML})
    service = WebEvidenceService(
        fetcher=fetcher,  # type: ignore[arg-type]
        robots_policy=AllowRobots(),  # type: ignore[arg-type]
        store=store,
        resolver=public_resolver,
    )
    monkeypatch.setattr(
        "cdm_desktop.services.web_evidence_service._wait_for_domain_delay",
        lambda *_args, **_kwargs: True,
    )

    initial_profile = CompanyProfile(legal_name="Temporary existing value")
    first = service.crawl(
        company_id="company:1",
        company_name="Example",
        seed_urls=["https://example.com/"],
        company_website="https://example.com/",
        profile=initial_profile,
        policy=CrawlPolicy(max_pages_per_domain=1, max_depth=0),
    )
    legal = next(
        candidate
        for candidate in first.profile_candidates
        if candidate.field_name == "legal_name"
    )
    assert legal.status == "pending"
    assert store.update_candidate_status(legal.id, "rejected")

    empty_profile = CompanyProfile()
    second = service.crawl(
        company_id="company:1",
        company_name="Example",
        seed_urls=["https://example.com/"],
        company_website="https://example.com/",
        profile=empty_profile,
        policy=CrawlPolicy(max_pages_per_domain=1, max_depth=0),
    )

    rejected = next(
        candidate
        for candidate in second.profile_candidates
        if candidate.field_name == "legal_name"
    )
    assert rejected.status == "rejected"
    assert empty_profile.legal_name == ""
    assert next(
        candidate
        for candidate in store.list_candidates("company:1")
        if candidate.id == rejected.id
    ).status == "rejected"
