from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from cdm_desktop.public_api.crawl_safety import BLOCKED_DOMAINS
from cdm_desktop.public_api.models import ProviderError
from cdm_desktop.security.url_safety import (
    FetchTooLargeError,
    UnsafeUrlError,
    safe_fetch_url,
)

WEB_EVIDENCE_PROVIDER_ID = "web_evidence"
WEB_EVIDENCE_USER_AGENT = "CompanyDecisionMonitorBot/0.1.5"


@dataclass(frozen=True, slots=True)
class WebFetchResponse:
    requested_url: str
    final_url: str
    content_type: str
    content: bytes
    text: str
    status_code: int


class SafeWebFetcher:
    """GET-only fetcher with URL validation before and after every redirect."""

    def __init__(
        self,
        *,
        timeout_seconds: int = 30,
        max_bytes: int = 5_000_000,
        resolver: Any | None = None,
        transport: httpx.BaseTransport | None = None,
        allow_localhost_for_dev: bool = False,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.resolver = resolver
        self.transport = transport
        self.allow_localhost_for_dev = allow_localhost_for_dev

    def fetch(
        self,
        url: str,
        *,
        allowed_domains: list[str] | None = None,
        blocked_domains: list[str] | None = None,
    ) -> tuple[WebFetchResponse | None, ProviderError | None]:
        try:
            fetched = safe_fetch_url(
                url,
                timeout_seconds=self.timeout_seconds,
                max_bytes=self.max_bytes,
                user_agent=WEB_EVIDENCE_USER_AGENT,
                resolver=self.resolver,
                transport=self.transport,
                allow_localhost_for_dev=self.allow_localhost_for_dev,
                allowed_domains=allowed_domains,
                blocked_domains=BLOCKED_DOMAINS | set(blocked_domains or []),
            )
        except UnsafeUrlError as exc:
            return None, ProviderError(
                WEB_EVIDENCE_PROVIDER_ID,
                "unsafe_url",
                str(exc),
                retryable=False,
            )
        except FetchTooLargeError as exc:
            return None, ProviderError(
                WEB_EVIDENCE_PROVIDER_ID,
                "response_too_large",
                str(exc),
                retryable=False,
            )
        except httpx.TimeoutException:
            return None, ProviderError(
                WEB_EVIDENCE_PROVIDER_ID,
                "network_timeout",
                "网页请求超时，请稍后重试。",
                retryable=True,
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            return None, ProviderError(
                WEB_EVIDENCE_PROVIDER_ID,
                "http_error",
                f"网页返回 HTTP {status_code}。",
                status_code=status_code,
                retryable=status_code >= 500,
            )
        except httpx.RequestError:
            return None, ProviderError(
                WEB_EVIDENCE_PROVIDER_ID,
                "network_error",
                "网页连接失败或 DNS 解析失败。",
                retryable=True,
            )
        text = _decode_text(fetched.content, fetched.content_type)
        return (
            WebFetchResponse(
                requested_url=fetched.url,
                final_url=fetched.final_url,
                content_type=fetched.content_type,
                content=fetched.content,
                text=text,
                status_code=fetched.status_code,
            ),
            None,
        )

    def get_text(
        self,
        _provider_id: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        allowed_domains: list[str] | None = None,
        blocked_domains: list[str] | None = None,
    ) -> tuple[str | None, ProviderError | None]:
        # Headers are intentionally ignored: cookies, tokens and caller-supplied
        # impersonation headers never enter the Web Evidence transport.
        _ = headers
        response, error = self.fetch(
            url,
            allowed_domains=allowed_domains,
            blocked_domains=blocked_domains,
        )
        return (response.text if response else None), error


def _decode_text(content: bytes, content_type: str) -> str:
    match = re.search(r"charset\s*=\s*[\"']?([^;\s\"']+)", content_type or "", re.I)
    candidates = [match.group(1) if match else "", "utf-8", "gb18030", "latin-1"]
    for encoding in candidates:
        if not encoding:
            continue
        try:
            return content.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return content.decode("utf-8", errors="replace")
