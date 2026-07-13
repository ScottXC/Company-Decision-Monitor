from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cdm_desktop.public_api.content_extractor import extract_web_evidence
from cdm_desktop.public_api.crawl_cache import WebEvidenceCache
from cdm_desktop.public_api.crawl_safety import validate_crawl_url
from cdm_desktop.public_api.http_client import PublicHttpClient
from cdm_desktop.public_api.robots_policy import CRAWLERGO_USER_AGENT, RobotsPolicy
from cdm_desktop.public_api.web_evidence_models import (
    CrawlJob,
    CrawlPolicy,
    CrawlResult,
    WebEvidenceItem,
    utc_now_iso,
)

PROVIDER_ID = "crawlergo_web_evidence"
DISPLAY_NAME = "网页证据采集"


@dataclass(frozen=True, slots=True)
class CrawlergoCommand:
    command: list[str]
    allowed_domains: list[str]
    timeout_seconds: int


def build_crawlergo_command(binary_path: str, seed_url: str, policy: CrawlPolicy) -> CrawlergoCommand:
    safe_binary = str(Path(binary_path))
    command = [
        safe_binary,
        "--output-mode",
        "json",
        "--max-crawled-count",
        str(policy.max_pages_per_domain),
        "--max-depth",
        str(policy.max_depth),
        seed_url,
    ]
    return CrawlergoCommand(command=command, allowed_domains=list(policy.allowed_domains), timeout_seconds=policy.timeout_seconds)


class CrawlergoWebEvidenceProvider:
    def __init__(
        self,
        *,
        crawlergo_path: str = "",
        http: PublicHttpClient | None = None,
        robots_policy: RobotsPolicy | None = None,
        cache: WebEvidenceCache | None = None,
    ) -> None:
        self.crawlergo_path = crawlergo_path.strip()
        self.http = http or PublicHttpClient(user_agent=CRAWLERGO_USER_AGENT)
        self.robots_policy = robots_policy or RobotsPolicy(self.http)
        self.cache = cache or WebEvidenceCache()

    def dependency_status(self) -> tuple[str, str]:
        if not self.crawlergo_path:
            return "dependency_missing", "crawlergo 未安装或未配置路径。可在高级设置中配置二进制路径。"
        path = Path(self.crawlergo_path)
        if not path.exists() or not path.is_file():
            return "dependency_missing", "crawlergo 路径不存在或不是可执行文件。"
        return "enabled", "crawlergo 已配置。"

    def crawl(
        self,
        *,
        company_name: str,
        seed_urls: list[str],
        policy: CrawlPolicy,
        progress_callback: Any | None = None,
        cancel_event: threading.Event | None = None,
    ) -> CrawlResult:
        job = CrawlJob(
            id=f"crawl:{int(time.time())}",
            company_name=company_name,
            seed_urls=seed_urls,
            allowed_domains=policy.allowed_domains,
            max_pages=policy.max_pages_per_domain,
            max_depth=policy.max_depth,
            timeout_seconds=policy.timeout_seconds,
            respect_robots=True,
            status="running",
            started_at=utc_now_iso(),
        )
        state, message = self.dependency_status()
        if state == "dependency_missing":
            job.status = "failed"
            job.finished_at = utc_now_iso()
            job.errors.append(message)
            return CrawlResult(job=job, error_message=message, diagnostics=[message])

        result = CrawlResult(job=job)
        allowed_domains = _allowed_domains(seed_urls, policy)
        policy.allowed_domains[:] = allowed_domains
        last_request_at: dict[str, float] = {}
        self._progress(progress_callback, 0, max(1, len(seed_urls)), "准备网页证据采集")

        for seed_index, seed_url in enumerate(seed_urls):
            if cancel_event and cancel_event.is_set():
                result.diagnostics.append("用户已取消采集。")
                job.status = "cancelled"
                break
            safety = validate_crawl_url(seed_url, allowed_domains=allowed_domains, blocked_domains=policy.blocked_domains)
            if not safety.allowed:
                result.skipped_urls.append({"url": seed_url, "reason": safety.reason})
                job.pages_skipped += 1
                continue
            robots = self.robots_policy.can_fetch(seed_url) if policy.respect_robots else None
            if robots and not robots.allowed:
                result.skipped_urls.append({"url": seed_url, "reason": robots.error_message})
                job.pages_skipped += 1
                continue
            discovered = self._run_crawlergo(seed_url, policy, result)
            urls = _dedupe_urls([seed_url, *discovered])[: policy.max_pages_per_domain]
            result.discovered_urls.extend(urls)
            for index, url in enumerate(urls):
                if cancel_event and cancel_event.is_set():
                    result.diagnostics.append("用户已取消采集。")
                    job.status = "cancelled"
                    break
                depth = 0 if url == seed_url else 1
                if depth > policy.max_depth:
                    result.skipped_urls.append({"url": url, "reason": "超过最大抓取深度。"})
                    job.pages_skipped += 1
                    continue
                item = self._extract_one(
                    url,
                    company_name=company_name,
                    crawl_depth=depth,
                    policy=policy,
                    last_request_at=last_request_at,
                    result=result,
                )
                if item:
                    result.items.append(item)
                    job.pages_crawled += 1
                self._progress(progress_callback, index + 1, len(urls), f"正在处理 {urlparse(url).hostname or url}")
            self._progress(progress_callback, seed_index + 1, max(1, len(seed_urls)), "种子 URL 处理完成")

        job.pages_discovered = len(set(result.discovered_urls))
        if job.status == "cancelled":
            pass
        elif result.items and result.skipped_urls:
            job.status = "partial"
        elif result.items:
            job.status = "success"
        else:
            job.status = "failed" if result.skipped_urls or result.diagnostics else "empty"
        job.finished_at = utc_now_iso()
        return result

    def _run_crawlergo(self, seed_url: str, policy: CrawlPolicy, result: CrawlResult) -> list[str]:
        command = build_crawlergo_command(self.crawlergo_path, seed_url, policy)
        try:
            completed = subprocess.run(
                command.command,
                capture_output=True,
                check=False,
                shell=False,
                text=True,
                timeout=policy.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            result.diagnostics.append("crawlergo 执行超时。")
            return []
        except OSError:
            result.diagnostics.append("crawlergo 启动失败，请检查二进制路径。")
            return []
        if completed.returncode != 0:
            result.diagnostics.append("crawlergo 返回非零状态，已保留种子 URL 继续安全提取。")
        return parse_crawlergo_urls(completed.stdout)

    def _extract_one(
        self,
        url: str,
        *,
        company_name: str,
        crawl_depth: int,
        policy: CrawlPolicy,
        last_request_at: dict[str, float],
        result: CrawlResult,
    ) -> WebEvidenceItem | None:
        safety = validate_crawl_url(url, allowed_domains=policy.allowed_domains, blocked_domains=policy.blocked_domains)
        if not safety.allowed:
            result.skipped_urls.append({"url": url, "reason": safety.reason})
            return None
        robots = self.robots_policy.can_fetch(url) if policy.respect_robots else None
        if robots and not robots.allowed:
            result.skipped_urls.append({"url": url, "reason": robots.error_message})
            return None
        cached = self.cache.get(url)
        if cached:
            cached.company_name = company_name
            cached.from_cache = True
            return cached
        robots_delay = robots.crawl_delay_seconds if robots and robots.crawl_delay_seconds is not None else 0
        delay = max(policy.request_delay_seconds, robots_delay, 1.0)
        _respect_delay(safety.domain, last_request_at, delay)
        html, error = self.http.get_text(PROVIDER_ID, url, headers={"User-Agent": CRAWLERGO_USER_AGENT})
        if error:
            result.skipped_urls.append({"url": url, "reason": error.message})
            return None
        item = extract_web_evidence(
            html or "",
            source_url=url,
            final_url=url,
            company_name=company_name,
            crawl_depth=crawl_depth,
            robots_allowed=not robots or robots.allowed,
        )
        self.cache.set(item, ttl_seconds=policy.cache_ttl_seconds)
        return item

    def _progress(self, callback: Any | None, current: int, total: int, message: str) -> None:
        if callback:
            callback(current, max(total, 1), message)


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
            if key.lower() in {"url", "target", "link"} and isinstance(value, str):
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


def _allowed_domains(seed_urls: list[str], policy: CrawlPolicy) -> list[str]:
    domains = {item.lower().strip(".") for item in policy.allowed_domains if item}
    for url in seed_urls:
        host = (urlparse(url).hostname or "").lower().strip(".")
        if host:
            domains.add(host)
    return sorted(domains)


def _respect_delay(domain: str, last_request_at: dict[str, float], delay_seconds: float) -> None:
    now = time.monotonic()
    last = last_request_at.get(domain)
    if last is not None:
        wait = delay_seconds - (now - last)
        if wait > 0:
            time.sleep(wait)
    last_request_at[domain] = time.monotonic()
