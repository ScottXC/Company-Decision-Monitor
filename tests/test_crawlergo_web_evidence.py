from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.content_extractor import extract_web_evidence
from cdm_desktop.public_api.crawl_cache import WebEvidenceCache
from cdm_desktop.public_api.crawl_safety import validate_crawl_url
from cdm_desktop.public_api.crawlergo_provider import (
    CrawlergoWebEvidenceProvider,
    build_crawlergo_command,
    parse_crawlergo_urls,
)
from cdm_desktop.public_api.models import ProviderError
from cdm_desktop.public_api.robots_policy import RobotsDecision, evaluate_robots_text
from cdm_desktop.public_api.web_evidence_models import CrawlPolicy


def make_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        raw_documents_dir=tmp_path / "raw_documents",
        exports_dir=tmp_path / "exports",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "cdm.db",
    ).ensure()


def test_robots_policy_allowed_disallowed_and_delay() -> None:
    robots = """
User-agent: *
Disallow: /private
Crawl-delay: 3
"""
    allowed = evaluate_robots_text(robots, "https://example.com/investors")
    blocked = evaluate_robots_text(robots, "https://example.com/private/page")

    assert allowed.allowed
    assert allowed.crawl_delay_seconds == 3
    assert not blocked.allowed
    assert "robots.txt" in blocked.error_message


def test_robots_missing_allows_low_frequency() -> None:
    class FakeHttp:
        def get_text(self, _provider: str, _url: str):
            return None, ProviderError("crawlergo_web_evidence", "http_error", "missing")

    provider = CrawlergoWebEvidenceProvider(robots_policy=None)
    provider.robots_policy.http = FakeHttp()  # type: ignore[assignment]
    decision = provider.robots_policy.can_fetch("https://example.com/")

    assert decision.allowed
    assert decision.missing_robots


def test_crawlergo_command_builder_is_list_and_limited(tmp_path: Path) -> None:
    binary = tmp_path / "crawlergo.exe"
    policy = CrawlPolicy(allowed_domains=["example.com"], max_pages_per_domain=7, max_depth=2, timeout_seconds=9)
    command = build_crawlergo_command(str(binary), "https://example.com", policy)

    assert isinstance(command.command, list)
    assert "--max-crawled-count" in command.command
    assert "7" in command.command
    assert "--max-depth" in command.command
    assert command.allowed_domains == ["example.com"]
    assert command.timeout_seconds == 9


def test_crawlergo_subprocess_uses_no_shell_and_filters_domains(tmp_path: Path, monkeypatch) -> None:
    binary = tmp_path / "crawlergo.exe"
    binary.write_text("placeholder", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["shell"] = kwargs.get("shell")
        return SimpleNamespace(returncode=0, stdout='{"req_list":[{"url":"https://example.com/ir"},{"url":"https://other.com/"}]}')

    class FakeHttp:
        def get_text(self, _provider: str, url: str, **_kwargs):
            if url.endswith("robots.txt"):
                return "User-agent: *\nAllow: /\n", None
            return "<html><head><title>IR</title><meta name='description' content='Investor relations'></head><body><main>Investor page text.</main></body></html>", None

    class FakeRobots:
        def can_fetch(self, _url: str) -> RobotsDecision:
            return RobotsDecision(True, "https://example.com/robots.txt")

    monkeypatch.setattr("cdm_desktop.public_api.crawlergo_provider.subprocess.run", fake_run)
    monkeypatch.setattr("cdm_desktop.public_api.crawlergo_provider.time.sleep", lambda _seconds: None)
    provider = CrawlergoWebEvidenceProvider(
        crawlergo_path=str(binary),
        http=FakeHttp(),  # type: ignore[arg-type]
        robots_policy=FakeRobots(),  # type: ignore[arg-type]
        cache=WebEvidenceCache(make_paths(tmp_path)),
    )
    result = provider.crawl(
        company_name="Example",
        seed_urls=["https://example.com"],
        policy=CrawlPolicy(max_pages_per_domain=5, max_depth=1),
    )

    assert captured["shell"] is False
    assert result.job.pages_crawled == 2
    assert any(item.domain == "example.com" for item in result.items)
    assert any(skip["url"] == "https://other.com/" for skip in result.skipped_urls)


def test_parse_crawlergo_urls_from_json_and_text() -> None:
    text = 'prefix {"req_list":[{"url":"https://example.com/a"}]} https://example.com/b'

    assert parse_crawlergo_urls(text) == ["https://example.com/a", "https://example.com/b"]


def test_url_validation_blocks_unsafe_targets() -> None:
    assert validate_crawl_url("https://example.com").allowed
    assert not validate_crawl_url("file:///etc/passwd").allowed
    assert not validate_crawl_url("javascript:alert(1)").allowed
    assert not validate_crawl_url("http://127.0.0.1").allowed
    assert not validate_crawl_url("https://xueqiu.com/S/AAPL").allowed
    assert not validate_crawl_url("https://other.com", allowed_domains=["example.com"]).allowed


def test_content_extractor_metadata_and_limits() -> None:
    html = """
<html lang="en"><head>
<title>Example IR</title>
<meta name="description" content="Company investor relations page">
<meta property="og:description" content="OG description">
<meta property="article:published_time" content="2026-01-01T00:00:00Z">
</head><body><main><h1>Investor Relations</h1><p>{body}</p></main></body></html>
""".format(body="Long text " * 200)

    item = extract_web_evidence(html, source_url="https://example.com/investor")

    assert item.title == "Example IR"
    assert item.description == "Company investor relations page"
    assert item.published_at == "2026-01-01T00:00:00Z"
    assert item.content_type == "investor_relations"
    assert len(item.content_snippet) <= 300
    assert len(item.extracted_text_preview) <= 800


def test_web_evidence_cache_stores_no_full_html(tmp_path: Path) -> None:
    cache = WebEvidenceCache(make_paths(tmp_path), ttl_seconds=60)
    item = extract_web_evidence(
        "<html><head><title>A</title></head><body>Full body text</body></html>",
        source_url="https://example.com/a",
    )
    cache.set(item)
    raw = next((tmp_path / "cache" / "web_evidence").glob("*.json")).read_text(encoding="utf-8")

    assert "<html" not in raw.lower()
    cached = cache.get("https://example.com/a")
    assert cached is not None
    assert cached.from_cache
    assert cache.clear() == 1


def test_crawlergo_ui_text_is_compliance_oriented() -> None:
    company_detail = Path("src/cdm_desktop/ui/pages/company_detail.py").read_text(encoding="utf-8")
    settings = Path("src/cdm_desktop/ui/pages/settings.py").read_text(encoding="utf-8")
    combined = company_detail + settings

    assert "robots" in combined
    assert "不绕过登录/验证码" in combined
    assert "抓取雪球" not in combined
    assert "cookie" not in combined.lower()
    assert "xq_a_token" not in combined.lower()
