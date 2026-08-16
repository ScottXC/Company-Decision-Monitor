from __future__ import annotations

import inspect
import socket
from pathlib import Path

from cdm_desktop.main import main
from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.crawlergo_provider import parse_crawlergo_urls
from cdm_desktop.public_api.crawlergo_runtime import (
    CRAWLERGO_DISCOVERY_ENABLED,
    CrawlergoRuntimeManager,
    build_crawlergo_command,
)
from cdm_desktop.public_api.models import ProviderError
from cdm_desktop.public_api.robots_policy import RobotsPolicy, evaluate_robots_text
from cdm_desktop.public_api.settings_store import PublicApiSettingsStore
from cdm_desktop.public_api.web_evidence_models import CrawlPolicy


def public_resolver(_host: str, _port: object, *, type: int = 0):
    _ = type
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def make_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        raw_documents_dir=tmp_path / "raw_documents",
        exports_dir=tmp_path / "exports",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "cdm.db",
    ).ensure()


def test_robots_policy_allowed_disallowed_and_decimal_delay() -> None:
    robots = """
User-agent: CompanyDecisionMonitorBot/0.1.5
Disallow: /private
Crawl-delay: 1.5
"""
    allowed = evaluate_robots_text(robots, "https://example.com/investors")
    blocked = evaluate_robots_text(robots, "https://example.com/private/page")

    assert allowed.allowed
    assert allowed.crawl_delay_seconds == 1.5
    assert not blocked.allowed
    assert "robots.txt" in blocked.error_message


def test_robots_missing_allows_low_frequency() -> None:
    class FakeHttp:
        def get_text(self, _provider: str, _url: str, **_kwargs):
            return None, ProviderError("web_evidence", "http_error", "missing")

    decision = RobotsPolicy(FakeHttp()).can_fetch("https://example.com/")

    assert decision.allowed
    assert decision.missing_robots
    assert "低频率" in decision.error_message


def test_robots_cache_uses_one_get_and_unsafe_redirect_fails_closed() -> None:
    class FakeHttp:
        def __init__(self) -> None:
            self.calls = 0

        def get_text(self, _provider: str, _url: str, **_kwargs):
            self.calls += 1
            return "User-agent: *\nAllow: /", None

    fake = FakeHttp()
    policy = RobotsPolicy(fake)
    assert policy.can_fetch("https://example.com/a").allowed
    assert policy.can_fetch("https://example.com/b").allowed
    assert fake.calls == 1

    class UnsafeRedirectHttp:
        def get_text(self, _provider: str, _url: str, **_kwargs):
            return None, ProviderError(
                "web_evidence",
                "unsafe_url",
                "该域名被安全策略禁止采集",
                retryable=False,
            )

    decision = RobotsPolicy(UnsafeRedirectHttp()).can_fetch("https://example.com/")
    assert not decision.allowed
    assert "不安全" in decision.error_message


def test_crawlergo_command_builder_is_argument_list_and_uses_supported_limits(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "crawlergo.exe"
    chrome = tmp_path / "chrome.exe"
    binary.write_bytes(b"binary")
    chrome.write_bytes(b"binary")
    policy = CrawlPolicy(
        allowed_domains=["example.com"],
        max_pages_per_domain=7,
        max_depth=2,
        timeout_seconds=9,
    )
    seed = "https://example.com/investors?a=1&b=two"
    command = build_crawlergo_command(
        str(binary),
        str(chrome),
        seed,
        policy,
        resolver=public_resolver,
    )

    assert isinstance(command.command, list)
    assert command.shell is False
    assert command.command[-1] == seed
    assert command.command[command.command.index("--max-crawled-count") + 1] == "7"
    assert command.command[command.command.index("--max-run-time") + 1] == "9"
    assert "--max-depth" not in command.command
    assert command.max_depth == 2
    assert command.allowed_domains == ["example.com"]


def test_crawlergo_runtime_external_and_license_blocked_bundled(tmp_path: Path) -> None:
    external_binary = tmp_path / "external" / "crawlergo.exe"
    external_chrome = tmp_path / "external" / "chrome.exe"
    external_binary.parent.mkdir()
    external_binary.write_bytes(b"binary")
    external_chrome.write_bytes(b"binary")
    empty_app = tmp_path / "app"
    empty_app.mkdir()

    external = CrawlergoRuntimeManager(
        external_binary_path=str(external_binary),
        external_chrome_path=str(external_chrome),
        app_dir=empty_app,
    ).discover()
    assert external.state == "enabled"
    assert external.mode == "external"
    assert not external.bundled

    bundled_binary = empty_app / "runtime" / "crawlergo" / "crawlergo.exe"
    bundled_chrome = empty_app / "runtime" / "chromium" / "chrome.exe"
    bundled_binary.parent.mkdir(parents=True)
    bundled_chrome.parent.mkdir(parents=True)
    bundled_binary.write_bytes(b"binary")
    bundled_chrome.write_bytes(b"binary")
    bundled = CrawlergoRuntimeManager(app_dir=empty_app).discover()
    assert bundled.mode == "bundled"
    assert bundled.state == "dependency_error"
    assert bundled.binary_status == "blocked_by_license_audit"


def test_crawlergo_runtime_calls_are_safe_and_discovery_disabled() -> None:
    source = inspect.getsource(CrawlergoRuntimeManager._run_diagnostic)

    assert "subprocess.Popen" in source
    assert "shell=False" in source
    assert CRAWLERGO_DISCOVERY_ENABLED is False


def test_parse_crawlergo_urls_from_json_and_text() -> None:
    text = 'prefix {"req_list":[{"url":"https://example.com/a"}]} https://example.com/b'

    assert parse_crawlergo_urls(text) == ["https://example.com/a", "https://example.com/b"]


def test_web_evidence_settings_defaults_and_robots_invariant(tmp_path: Path) -> None:
    store = PublicApiSettingsStore(make_paths(tmp_path))
    policy = store.crawlergo_policy()

    assert policy.max_pages_per_domain == 15
    assert policy.max_depth == 2
    assert policy.timeout_seconds == 30
    assert policy.request_delay_seconds >= 1
    assert policy.respect_robots

    policy.respect_robots = False
    store.set_crawlergo_policy(policy)
    assert store.crawlergo_policy().respect_robots


def test_web_evidence_ui_text_is_compliance_oriented() -> None:
    company_detail = Path("src/cdm_desktop/ui/pages/company_detail.py").read_text(encoding="utf-8")
    settings = Path("src/cdm_desktop/ui/pages/settings.py").read_text(encoding="utf-8")
    combined = company_detail + settings

    assert "网页证据" in combined
    assert "robots.txt 始终开启" in combined
    assert "不会绕过登录、验证码、Cookie、Token、付费墙或 robots.txt" in combined
    assert "采集官网" in combined
    assert "添加 URL" in combined
    assert "取消任务" in combined
    assert "采集诊断" in combined
    assert "原始 crawlergo stdout" not in combined
    assert "抓取雪球" not in combined


def test_optional_crawlergo_self_test_does_not_fail_when_dependency_is_missing(
    capsys,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CDM_DESKTOP_DATA_DIR", str(tmp_path))

    assert main(["--self-test", "crawlergo"]) == 0
    output = capsys.readouterr().out
    assert "crawlergo_optional_external" in output
    assert "binary_status=" in output
    assert "chrome_status=" in output
