from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class WebEvidenceItem:
    id: str
    company_id: str = ""
    company_name: str = ""
    source_url: str = ""
    final_url: str = ""
    domain: str = ""
    title: str = ""
    description: str = ""
    content_snippet: str = ""
    extracted_text_preview: str = ""
    content_type: str = "other"
    language: str = ""
    published_at: str = ""
    discovered_at: str = field(default_factory=utc_now_iso)
    crawled_at: str = field(default_factory=utc_now_iso)
    provider: str = "crawlergo_web_evidence"
    crawl_depth: int = 0
    robots_allowed: bool = True
    status: str = "ok"
    error_message: str = ""
    open_url: str = ""
    from_cache: bool = False

    @classmethod
    def create_id(cls, url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WebEvidenceItem:
        allowed = {field_name for field_name in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in data.items() if key in allowed})


@dataclass(slots=True)
class CrawlPolicy:
    respect_robots: bool = True
    allowed_domains: list[str] = field(default_factory=list)
    blocked_domains: list[str] = field(default_factory=list)
    max_pages_per_domain: int = 10
    max_depth: int = 1
    request_delay_seconds: float = 1.0
    timeout_seconds: int = 15
    allow_full_text_display: bool = False
    allow_third_party_full_text: bool = False
    cache_ttl_seconds: int = 86400


@dataclass(slots=True)
class CrawlJob:
    id: str
    company_name: str = ""
    seed_urls: list[str] = field(default_factory=list)
    allowed_domains: list[str] = field(default_factory=list)
    max_pages: int = 10
    max_depth: int = 1
    timeout_seconds: int = 15
    respect_robots: bool = True
    status: str = "pending"
    started_at: str = ""
    finished_at: str = ""
    pages_discovered: int = 0
    pages_crawled: int = 0
    pages_skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CrawlResult:
    job: CrawlJob
    items: list[WebEvidenceItem] = field(default_factory=list)
    discovered_urls: list[str] = field(default_factory=list)
    skipped_urls: list[dict[str, str]] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    error_message: str = ""

    @property
    def ok(self) -> bool:
        return self.job.status in {"success", "partial"} and not self.error_message
