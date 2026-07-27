from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.crawlergo_runtime import (
    CrawlergoCommand,
    CrawlergoRuntimeManager,
    CrawlergoRuntimeStatus,
    RuntimeTestResult,
)
from cdm_desktop.public_api.crawlergo_runtime import (
    build_crawlergo_command as _build_runtime_command,
)
from cdm_desktop.public_api.robots_policy import RobotsPolicy
from cdm_desktop.public_api.web_evidence_models import CrawlPolicy, CrawlResult
from cdm_desktop.public_api.web_evidence_store import WebEvidenceStore
from cdm_desktop.public_api.web_fetcher import SafeWebFetcher
from cdm_desktop.services.web_evidence_service import WebEvidenceService

PROVIDER_ID = "web_evidence"
DISPLAY_NAME = "网页证据"


def build_crawlergo_command(
    binary_path: str,
    seed_url: str,
    policy: CrawlPolicy,
    *,
    chrome_path: str = "",
    resolver: Any | None = None,
) -> CrawlergoCommand:
    return _build_runtime_command(
        binary_path,
        chrome_path,
        seed_url,
        policy,
        resolver=resolver,
    )


class CrawlergoWebEvidenceProvider:
    """Compatibility facade around the safe Web Evidence service.

    Crawlergo is detected and diagnosed as an optional external runtime. It is
    intentionally not launched for discovery because the audited upstream build
    cannot disable form submission and DOM event triggering.
    """

    def __init__(
        self,
        *,
        crawlergo_path: str = "",
        chrome_path: str = "",
        paths: AppPaths | None = None,
        http: SafeWebFetcher | None = None,
        robots_policy: RobotsPolicy | None = None,
        cache: object | None = None,
        store: WebEvidenceStore | None = None,
    ) -> None:
        _ = cache
        self.crawlergo_path = crawlergo_path.strip()
        self.runtime_manager = CrawlergoRuntimeManager(
            external_binary_path=self.crawlergo_path,
            external_chrome_path=chrome_path,
        )
        fetcher = http or SafeWebFetcher()
        self.service = WebEvidenceService(
            paths,
            fetcher=fetcher,
            robots_policy=robots_policy,
            store=store,
            runtime_manager=self.runtime_manager,
            resolver=getattr(fetcher, "resolver", None),
        )

    def runtime_status(self) -> CrawlergoRuntimeStatus:
        return self.runtime_manager.discover()

    def dependency_status(self) -> tuple[str, str]:
        status = self.runtime_status()
        return status.state, status.message

    def test_runtime(self) -> RuntimeTestResult:
        return self.runtime_manager.test_runtime()

    def crawl(
        self,
        *,
        company_name: str,
        seed_urls: list[str],
        policy: CrawlPolicy,
        company_id: str = "",
        company_website: str = "",
        profile: Any | None = None,
        progress_callback: Any | None = None,
        cancel_event: threading.Event | None = None,
    ) -> CrawlResult:
        return self.service.crawl(
            company_id=company_id or company_name.casefold().strip(),
            company_name=company_name,
            seed_urls=seed_urls,
            policy=policy,
            company_website=company_website,
            profile=profile,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

    def shutdown(self) -> None:
        self.service.shutdown()


def parse_crawlergo_urls(stdout: str) -> list[str]:
    text = stdout or ""
    urls: list[str] = []
    for payload in _json_candidates(text):
        urls.extend(_extract_urls_from_json(payload))
    urls.extend(re.findall(r"https?://[^\s\"'<>]+", text))
    return _dedupe_urls(urls)


def _json_candidates(text: str) -> list[Any]:
    candidates: list[Any] = []
    stripped = text.strip()
    for value in (stripped, _extract_json_fragment(stripped)):
        if not value:
            continue
        try:
            candidates.append(json.loads(value))
        except json.JSONDecodeError:
            continue
    return candidates


def _extract_json_fragment(text: str) -> str:
    start_candidates = [index for index in (text.find("{"), text.find("[")) if index >= 0]
    if not start_candidates:
        return ""
    start = min(start_candidates)
    end = max(text.rfind("}"), text.rfind("]"))
    return text[start : end + 1] if end > start else ""


def _extract_urls_from_json(payload: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(payload, str) and payload.startswith(("http://", "https://")):
        urls.append(payload)
    elif isinstance(payload, list):
        for item in payload:
            urls.extend(_extract_urls_from_json(item))
    elif isinstance(payload, dict):
        for key, value in payload.items():
            if key.casefold() in {"url", "target", "link"} and isinstance(value, str):
                urls.append(value)
            else:
                urls.extend(_extract_urls_from_json(value))
    return urls


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        clean = url.strip().rstrip(".,;)")
        if clean in seen or not clean.startswith(("http://", "https://")):
            continue
        seen.add(clean)
        result.append(clean)
    return result


def runtime_path_is_file(path: str) -> bool:
    """Small test hook that never executes a configured binary."""
    return bool(path and Path(path).expanduser().is_file())
