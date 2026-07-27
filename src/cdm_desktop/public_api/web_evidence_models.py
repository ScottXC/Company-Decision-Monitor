from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

CONTENT_TYPES = {
    "company_homepage",
    "investor_relations",
    "press_release",
    "announcement",
    "financial_report",
    "annual_report",
    "official_news",
    "official_blog",
    "product",
    "careers",
    "third_party_news",
    "other",
}

DISPLAY_MODES = {"full_cleaned_text", "excerpt_only", "metadata_only"}
CANDIDATE_STATUSES = {"pending", "accepted", "rejected", "auto_accepted"}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class WebEvidenceItem:
    id: str
    company_id: str = ""
    company_name: str = ""
    source_url: str = ""
    final_url: str = ""
    canonical_url: str = ""
    domain: str = ""
    title: str = ""
    description: str = ""
    meta_description: str = ""
    og_title: str = ""
    og_description: str = ""
    h1: str = ""
    cleaned_text: str = ""
    content_snippet: str = ""
    extracted_text_preview: str = ""
    content_type: str = "other"
    language: str = ""
    site_name: str = ""
    author: str = ""
    published_at: str = ""
    modified_at: str = ""
    discovered_at: str = field(default_factory=utc_now_iso)
    crawled_at: str = field(default_factory=utc_now_iso)
    robots_allowed: bool = True
    is_official_domain: bool = False
    display_mode: str = "excerpt_only"
    provider: str = "web_evidence"
    content_hash: str = ""
    from_cache: bool = False
    status: str = "ok"
    error_message: str = ""
    headings: list[str] = field(default_factory=list)
    links: list[dict[str, str]] = field(default_factory=list)
    json_ld: list[dict[str, Any]] = field(default_factory=list)
    structured_data: dict[str, Any] = field(default_factory=dict)
    crawl_depth: int = 0
    open_url: str = ""

    def __post_init__(self) -> None:
        if self.content_type not in CONTENT_TYPES:
            self.content_type = "other"
        if self.display_mode not in DISPLAY_MODES:
            self.display_mode = "excerpt_only"
        if not self.final_url:
            self.final_url = self.source_url
        if not self.canonical_url:
            self.canonical_url = self.final_url or self.source_url
        if not self.open_url:
            self.open_url = self.final_url or self.source_url
        if not self.content_hash:
            self.content_hash = self.create_content_hash(
                self.cleaned_text or self.content_snippet or self.canonical_url
            )

    @classmethod
    def create_id(cls, url: str, company_id: str = "") -> str:
        identity = f"{company_id.strip()}\n{url.strip()}"
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    @staticmethod
    def create_content_hash(content: str) -> str:
        return hashlib.sha256((content or "").encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WebEvidenceItem:
        allowed = {field_name for field_name in cls.__dataclass_fields__}
        values = {key: value for key, value in data.items() if key in allowed}
        for name in ("headings", "links", "json_ld"):
            if not isinstance(values.get(name), list):
                values[name] = []
        if not isinstance(values.get("structured_data"), dict):
            values["structured_data"] = {}
        return cls(**values)


@dataclass(slots=True)
class CrawlPolicy:
    respect_robots: bool = True
    allowed_domains: list[str] = field(default_factory=list)
    blocked_domains: list[str] = field(default_factory=list)
    max_pages_per_domain: int = 15
    max_depth: int = 2
    request_delay_seconds: float = 1.0
    timeout_seconds: int = 30
    same_domain_only: bool = True
    allow_full_text_display: bool = True
    allow_third_party_full_text: bool = False
    cache_ttl_seconds: int = 86400
    max_content_chars: int = 100_000
    dev_allow_localhost: bool = False

    def __post_init__(self) -> None:
        # robots.txt is a non-configurable product invariant.
        self.respect_robots = True
        self.max_pages_per_domain = max(1, min(50, int(self.max_pages_per_domain)))
        self.max_depth = max(0, min(3, int(self.max_depth)))
        self.request_delay_seconds = max(1.0, float(self.request_delay_seconds))
        self.timeout_seconds = max(5, min(120, int(self.timeout_seconds)))
        self.cache_ttl_seconds = max(3600, min(604800, int(self.cache_ttl_seconds)))
        self.max_content_chars = max(2_000, min(500_000, int(self.max_content_chars)))


@dataclass(slots=True)
class CrawlJob:
    id: str
    company_id: str = ""
    company_name: str = ""
    seed_url: str = ""
    seed_urls: list[str] = field(default_factory=list)
    allowed_domains: list[str] = field(default_factory=list)
    max_pages: int = 15
    max_depth: int = 2
    timeout_seconds: int = 30
    request_delay_seconds: float = 1.0
    status: str = "pending"
    progress: int = 0
    pages_discovered: int = 0
    pages_processed: int = 0
    pages_skipped: int = 0
    started_at: str = ""
    finished_at: str = ""
    cancelled: bool = False
    error_type: str = ""
    error_message: str = ""
    errors: list[str] = field(default_factory=list)
    respect_robots: bool = True

    def __post_init__(self) -> None:
        self.respect_robots = True
        if not self.seed_url and self.seed_urls:
            self.seed_url = self.seed_urls[0]
        if not self.seed_urls and self.seed_url:
            self.seed_urls = [self.seed_url]

    @property
    def pages_crawled(self) -> int:
        return self.pages_processed

    @pages_crawled.setter
    def pages_crawled(self, value: int) -> None:
        self.pages_processed = int(value)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ProfileFieldCandidate:
    field_name: str
    proposed_value: Any
    source_url: str
    evidence_id: str
    confidence: float
    current_value: Any = ""
    status: str = "pending"
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if self.status not in CANDIDATE_STATUSES:
            self.status = "pending"
        self.confidence = max(0.0, min(1.0, float(self.confidence)))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProfileFieldCandidate:
        values = {
            name: data.get(name)
            for name in cls.__dataclass_fields__
            if name in data
        }
        return cls(**values)

    def proposed_value_json(self) -> str:
        return json.dumps(self.proposed_value, ensure_ascii=False, sort_keys=True)


@dataclass(slots=True)
class CrawlResult:
    job: CrawlJob
    items: list[WebEvidenceItem] = field(default_factory=list)
    profile_candidates: list[ProfileFieldCandidate] = field(default_factory=list)
    discovered_urls: list[str] = field(default_factory=list)
    skipped_urls: list[dict[str, str]] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    error_message: str = ""

    @property
    def ok(self) -> bool:
        return self.job.status in {"success", "partial"} and not self.error_message
