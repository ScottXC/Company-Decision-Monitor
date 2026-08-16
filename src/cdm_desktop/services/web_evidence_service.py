from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.content_extractor import (
    extract_pdf_evidence,
    extract_web_evidence,
)
from cdm_desktop.public_api.crawl_safety import (
    canonicalize_crawl_url,
    crawl_skip_reason,
    is_pdf_url,
    same_registered_domain,
    validate_crawl_url,
)
from cdm_desktop.public_api.crawlergo_runtime import CrawlergoRuntimeManager
from cdm_desktop.public_api.models import CompanyProfile
from cdm_desktop.public_api.profile_candidates import (
    apply_auto_accepted_candidates,
    profile_candidates_from_evidence,
)
from cdm_desktop.public_api.robots_policy import RobotsPolicy
from cdm_desktop.public_api.web_evidence_models import (
    CrawlJob,
    CrawlPolicy,
    CrawlResult,
    WebEvidenceItem,
    utc_now_iso,
)
from cdm_desktop.public_api.web_evidence_store import WebEvidenceStore
from cdm_desktop.public_api.web_fetcher import SafeWebFetcher

ProgressCallback = Callable[[int, int, str], None]

PRIORITY_PATH_MARKERS = (
    "/investor-relations",
    "/investors",
    "/investor",
    "/ir",
    "/press-releases",
    "/press",
    "/announcements",
    "/reports",
    "/financials",
    "/news",
    "/blog",
    "/media",
    "/events",
)


@dataclass(frozen=True, slots=True)
class _QueuedUrl:
    url: str
    depth: int
    source_url: str


class WebEvidenceService:
    """User-triggered, GET-only public web collection independent from search workers."""

    def __init__(
        self,
        paths: AppPaths | None = None,
        *,
        fetcher: SafeWebFetcher | None = None,
        robots_policy: RobotsPolicy | None = None,
        store: WebEvidenceStore | None = None,
        runtime_manager: CrawlergoRuntimeManager | None = None,
        resolver: Any | None = None,
    ) -> None:
        self.resolver = resolver
        self.fetcher = fetcher or SafeWebFetcher(resolver=resolver)
        self.robots_policy = robots_policy or RobotsPolicy(self.fetcher)
        self.store = store or WebEvidenceStore(paths)
        self.runtime_manager = runtime_manager or CrawlergoRuntimeManager()
        self._job_slots = threading.BoundedSemaphore(2)
        self._domain_locks: dict[str, threading.Lock] = {}
        self._domain_locks_guard = threading.Lock()
        self._active_cancel_events: set[threading.Event] = set()
        self._active_guard = threading.Lock()

    def crawl(
        self,
        *,
        company_id: str,
        company_name: str,
        seed_urls: list[str],
        policy: CrawlPolicy,
        company_website: str = "",
        profile: CompanyProfile | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> CrawlResult:
        event = cancel_event or threading.Event()
        job = CrawlJob(
            id=f"crawl:{uuid.uuid4().hex}",
            company_id=company_id,
            company_name=company_name,
            seed_url=next((url for url in seed_urls if url.strip()), ""),
            seed_urls=[url.strip() for url in seed_urls if url.strip()],
            allowed_domains=list(policy.allowed_domains),
            max_pages=policy.max_pages_per_domain,
            max_depth=policy.max_depth,
            timeout_seconds=policy.timeout_seconds,
            request_delay_seconds=policy.request_delay_seconds,
            status="pending",
        )
        result = CrawlResult(job=job)
        if not job.seed_urls:
            return self._fail(result, "invalid_url", "请先输入公司官网或公开网页 URL。")
        if not self._acquire_slot(event):
            return self._cancel(result)

        with self._active_guard:
            self._active_cancel_events.add(event)
        try:
            return self._crawl_locked(
                result,
                policy=policy,
                company_website=company_website,
                profile=profile,
                progress_callback=progress_callback,
                cancel_event=event,
            )
        finally:
            with self._active_guard:
                self._active_cancel_events.discard(event)
            self._job_slots.release()

    def list_evidence(self, company_id: str) -> list[WebEvidenceItem]:
        return self.store.list_evidence(company_id)

    def delete_evidence(self, evidence_id: str) -> bool:
        return self.store.delete_evidence(evidence_id)

    def clear_company(self, company_id: str) -> int:
        return self.store.clear_company(company_id)

    def clear_all(self) -> int:
        return self.store.clear_all()

    def shutdown(self) -> None:
        with self._active_guard:
            events = list(self._active_cancel_events)
        for event in events:
            event.set()
        self.runtime_manager.terminate_all()

    def _crawl_locked(
        self,
        result: CrawlResult,
        *,
        policy: CrawlPolicy,
        company_website: str,
        profile: CompanyProfile | None,
        progress_callback: ProgressCallback | None,
        cancel_event: threading.Event,
    ) -> CrawlResult:
        job = result.job
        valid_seeds, allowed_domains = self._validate_seeds(job.seed_urls, policy, result)
        job.allowed_domains = allowed_domains
        if not valid_seeds:
            return self._finish(result)
        job.status = "running"
        job.started_at = utc_now_iso()
        self.store.save_job(job)
        self._progress(progress_callback, 0, job.max_pages, "正在检查网页安全策略与 robots.txt")

        # A manually entered URL is not silently promoted to an official domain.
        official_domain = _hostname(company_website)
        queue: deque[_QueuedUrl] = deque(
            _QueuedUrl(seed, 0, seed) for seed in valid_seeds
        )
        queued = {canonicalize_crawl_url(seed) for seed in valid_seeds}
        result.discovered_urls.extend(valid_seeds)
        processed: set[str] = set()
        last_request_at: dict[str, float] = {}
        deadline = time.monotonic() + policy.timeout_seconds

        while queue and job.pages_processed < job.max_pages:
            if cancel_event.is_set():
                return self._cancel(result)
            if time.monotonic() >= deadline:
                job.error_type = "timeout"
                job.error_message = "网页证据任务达到总超时限制。"
                result.diagnostics.append(job.error_message)
                break
            queued_url = queue.popleft()
            canonical = canonicalize_crawl_url(queued_url.url)
            if canonical in processed:
                continue
            processed.add(canonical)
            job.pages_discovered = len(queued)
            job.pages_processed += 1

            item = self._process_url(
                queued_url,
                result=result,
                policy=policy,
                official_domain=official_domain,
                last_request_at=last_request_at,
                cancel_event=cancel_event,
                deadline=deadline,
            )
            if item is None:
                job.progress = min(
                    100,
                    round(job.pages_processed * 100 / max(1, job.max_pages)),
                )
                self.store.save_job(job)
                continue

            result.items.append(item)
            job.progress = min(100, round(job.pages_processed * 100 / max(1, job.max_pages)))
            candidates = profile_candidates_from_evidence(item, profile)
            persisted_statuses = {
                candidate.id: candidate.status
                for candidate in self.store.list_candidates(job.company_id)
            }
            for candidate in candidates:
                if persisted_statuses.get(candidate.id) in {"accepted", "rejected"}:
                    candidate.status = persisted_statuses[candidate.id]
            if profile is not None:
                apply_auto_accepted_candidates(profile, candidates)
            for candidate in candidates:
                self.store.save_candidate(job.company_id, candidate)
            result.profile_candidates.extend(candidates)

            if queued_url.depth < policy.max_depth and item.display_mode != "metadata_only":
                for link in _prioritized_links(item.links):
                    link_url = str(link.get("url") or "")
                    normalized = canonicalize_crawl_url(link_url)
                    if normalized in processed or normalized in queued:
                        continue
                    if policy.same_domain_only and not same_registered_domain(
                        link_url, _hostname(queued_url.source_url)
                    ):
                        self._skip(result, link_url, "默认仅采集同域名公开页面。")
                        continue
                    safety = validate_crawl_url(
                        link_url,
                        allowed_domains=allowed_domains,
                        blocked_domains=policy.blocked_domains,
                        dev_mode=policy.dev_allow_localhost,
                        resolver=self.resolver,
                    )
                    reason = safety.reason if not safety.allowed else crawl_skip_reason(link_url)
                    if reason:
                        self._skip(result, link_url, reason)
                        continue
                    queued.add(normalized)
                    queue.append(_QueuedUrl(link_url, queued_url.depth + 1, queued_url.source_url))
                    result.discovered_urls.append(link_url)
                    if len(queued) >= job.max_pages * 8:
                        break

            self.store.save_job(job)
            self._progress(
                progress_callback,
                job.pages_processed,
                job.max_pages,
                f"已处理 {job.pages_processed} 页 · {item.domain}",
            )

        return self._finish(result)

    def _process_url(
        self,
        queued: _QueuedUrl,
        *,
        result: CrawlResult,
        policy: CrawlPolicy,
        official_domain: str,
        last_request_at: dict[str, float],
        cancel_event: threading.Event,
        deadline: float,
    ) -> WebEvidenceItem | None:
        job = result.job
        safety = validate_crawl_url(
            queued.url,
            allowed_domains=job.allowed_domains,
            blocked_domains=policy.blocked_domains,
            dev_mode=policy.dev_allow_localhost,
            resolver=self.resolver,
        )
        if not safety.allowed:
            self._skip(result, queued.url, safety.reason)
            return None
        skip_reason = crawl_skip_reason(safety.normalized_url)
        if skip_reason:
            self._skip(result, queued.url, skip_reason)
            return None

        request_domains = [safety.domain] if policy.same_domain_only else job.allowed_domains
        robots = self.robots_policy.can_fetch(
            safety.normalized_url,
            allowed_domains=request_domains,
            blocked_domains=policy.blocked_domains,
        )
        if not robots.allowed:
            self._skip(result, queued.url, robots.error_message, error_type="robots_blocked")
            return None
        is_official = bool(
            official_domain and same_registered_domain(safety.normalized_url, official_domain)
        )
        if is_pdf_url(safety.normalized_url):
            item = extract_pdf_evidence(
                source_url=queued.url,
                final_url=safety.normalized_url,
                company_id=job.company_id,
                company_name=job.company_name,
                crawl_depth=queued.depth,
                robots_allowed=True,
                is_official_domain=is_official,
            )
            return self.store.save_evidence(item, ttl_seconds=policy.cache_ttl_seconds)

        cached = self.store.cached_evidence(job.company_id, safety.normalized_url)
        if cached:
            result.diagnostics.append(f"缓存命中：{safety.normalized_url}")
            return cached

        domain_lock = self._domain_lock(safety.domain)
        if not self._acquire_domain_lock(domain_lock, cancel_event, deadline):
            if cancel_event.is_set():
                job.cancelled = True
                job.error_type = "cancelled"
                job.error_message = "用户已取消网页证据任务。"
                return None
            self._skip(result, queued.url, "等待同域任务时达到总超时限制。", error_type="timeout")
            return None
        try:
            robots_delay = robots.crawl_delay_seconds or 0.0
            delay = max(1.0, policy.request_delay_seconds, robots_delay)
            if not _wait_for_domain_delay(
                safety.domain,
                last_request_at,
                delay,
                cancel_event,
                deadline,
            ):
                if cancel_event.is_set():
                    job.cancelled = True
                    job.error_type = "cancelled"
                    job.error_message = "用户已取消网页证据任务。"
                else:
                    job.error_type = "timeout"
                    job.error_message = "网页证据任务达到总超时限制。"
                return None
            response, error = self.fetcher.fetch(
                safety.normalized_url,
                allowed_domains=request_domains,
                blocked_domains=policy.blocked_domains,
            )
            last_request_at[safety.domain] = time.monotonic()
        finally:
            domain_lock.release()
        if error:
            self._skip(result, queued.url, error.message, error_type=error.state)
            return None
        if response is None:
            self._skip(result, queued.url, "网页未返回可处理内容。", error_type="empty")
            return None

        final_safety = validate_crawl_url(
            response.final_url,
            allowed_domains=job.allowed_domains,
            blocked_domains=policy.blocked_domains,
            dev_mode=policy.dev_allow_localhost,
            resolver=self.resolver,
        )
        if not final_safety.allowed:
            self._skip(result, response.final_url, final_safety.reason, error_type="unsafe_redirect")
            return None
        is_official = bool(
            official_domain
            and same_registered_domain(final_safety.normalized_url, official_domain)
        )
        content_type = response.content_type.casefold()
        if "application/pdf" in content_type:
            item = extract_pdf_evidence(
                source_url=queued.url,
                final_url=final_safety.normalized_url,
                company_id=job.company_id,
                company_name=job.company_name,
                crawl_depth=queued.depth,
                robots_allowed=True,
                is_official_domain=is_official,
            )
            return self.store.save_evidence(item, ttl_seconds=policy.cache_ttl_seconds)
        if not any(marker in content_type for marker in ("text/html", "application/xhtml", "text/plain")):
            self._skip(result, queued.url, "响应不是 HTML、文本或 PDF，已跳过。")
            return None

        item = extract_web_evidence(
            response.text,
            source_url=queued.url,
            final_url=final_safety.normalized_url,
            company_id=job.company_id,
            company_name=job.company_name,
            crawl_depth=queued.depth,
            robots_allowed=True,
            is_official_domain=is_official,
            max_content_chars=policy.max_content_chars,
        )
        canonical_safety = validate_crawl_url(
            item.canonical_url,
            allowed_domains=job.allowed_domains,
            blocked_domains=policy.blocked_domains,
            dev_mode=policy.dev_allow_localhost,
            resolver=self.resolver,
        )
        if not canonical_safety.allowed:
            item.canonical_url = final_safety.normalized_url
            item.id = WebEvidenceItem.create_id(item.canonical_url, job.company_id)
        return self.store.save_evidence(item, ttl_seconds=policy.cache_ttl_seconds)

    def _validate_seeds(
        self,
        seeds: list[str],
        policy: CrawlPolicy,
        result: CrawlResult,
    ) -> tuple[list[str], list[str]]:
        domains = {
            value.casefold().strip(".")
            for value in policy.allowed_domains
            if value.strip()
        }
        for seed in seeds:
            host = _hostname(seed)
            if host:
                domains.add(host)
        allowed_domains = sorted(domains)
        valid: list[str] = []
        for seed in seeds:
            safety = validate_crawl_url(
                seed,
                allowed_domains=allowed_domains,
                blocked_domains=policy.blocked_domains,
                dev_mode=policy.dev_allow_localhost,
                resolver=self.resolver,
            )
            if not safety.allowed:
                self._skip(result, seed, safety.reason, error_type="unsafe_url")
                continue
            valid.append(safety.normalized_url)
        return list(dict.fromkeys(valid)), allowed_domains

    def _finish(self, result: CrawlResult) -> CrawlResult:
        job = result.job
        if job.cancelled:
            job.status = "cancelled"
        elif result.items and (result.skipped_urls or job.error_type):
            job.status = "partial"
        elif result.items:
            job.status = "success"
        elif job.error_type:
            job.status = "failed"
        elif result.skipped_urls:
            job.status = "blocked"
        else:
            job.status = "empty"
        job.finished_at = utc_now_iso()
        job.progress = 100 if job.status in {"success", "partial", "empty", "blocked"} else job.progress
        self.store.save_job(job)
        result.error_message = job.error_message
        return result

    def _fail(self, result: CrawlResult, error_type: str, message: str) -> CrawlResult:
        result.job.error_type = error_type
        result.job.error_message = message
        result.diagnostics.append(message)
        return self._finish(result)

    def _cancel(self, result: CrawlResult) -> CrawlResult:
        result.job.cancelled = True
        result.job.error_type = "cancelled"
        result.job.error_message = "用户已取消网页证据任务。"
        result.diagnostics.append(result.job.error_message)
        return self._finish(result)

    def _skip(
        self,
        result: CrawlResult,
        url: str,
        reason: str,
        *,
        error_type: str = "skipped",
    ) -> None:
        result.skipped_urls.append({"url": url, "reason": reason, "type": error_type})
        result.job.pages_skipped += 1
        self.store.record_error(result.job.id, url, error_type, reason)

    def _progress(
        self,
        callback: ProgressCallback | None,
        current: int,
        total: int,
        message: str,
    ) -> None:
        if callback:
            callback(current, max(1, total), message)

    def _acquire_slot(self, cancel_event: threading.Event) -> bool:
        while not cancel_event.is_set():
            if self._job_slots.acquire(timeout=0.1):
                return True
        return False

    def _domain_lock(self, domain: str) -> threading.Lock:
        with self._domain_locks_guard:
            return self._domain_locks.setdefault(domain, threading.Lock())

    @staticmethod
    def _acquire_domain_lock(
        lock: threading.Lock,
        cancel_event: threading.Event,
        deadline: float,
    ) -> bool:
        while not cancel_event.is_set() and time.monotonic() < deadline:
            if lock.acquire(timeout=0.1):
                return True
        return False


def _hostname(url: str) -> str:
    return (urlsplit(url).hostname or "").casefold().strip(".")


def _prioritized_links(links: list[dict[str, str]]) -> list[dict[str, str]]:
    def score(link: dict[str, str]) -> tuple[int, str]:
        url = str(link.get("url") or "").casefold()
        try:
            priority = next(
                index for index, marker in enumerate(PRIORITY_PATH_MARKERS) if marker in url
            )
        except StopIteration:
            priority = len(PRIORITY_PATH_MARKERS)
        return priority, url

    return sorted(links, key=score)


def _wait_for_domain_delay(
    domain: str,
    last_request_at: dict[str, float],
    delay_seconds: float,
    cancel_event: threading.Event,
    deadline: float,
) -> bool:
    last = last_request_at.get(domain)
    if last is None:
        return not cancel_event.is_set()
    wait_seconds = max(0.0, delay_seconds - (time.monotonic() - last))
    wait_seconds = min(wait_seconds, max(0.0, deadline - time.monotonic()))
    return not cancel_event.wait(wait_seconds) and time.monotonic() < deadline
