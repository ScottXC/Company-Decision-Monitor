from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse

BLOCKED_DOMAINS = {
    "xueqiu.com",
    "www.xueqiu.com",
    "mp.weixin.qq.com",
    "weixin.qq.com",
    "facebook.com",
    "www.facebook.com",
    "x.com",
    "twitter.com",
    "weibo.com",
    "www.weibo.com",
}

BLOCKED_HOST_SUFFIXES = (
    ".xueqiu.com",
    ".weixin.qq.com",
    ".facebook.com",
    ".twitter.com",
    ".weibo.com",
)


@dataclass(frozen=True, slots=True)
class UrlSafetyResult:
    allowed: bool
    reason: str = ""
    normalized_url: str = ""
    domain: str = ""


def validate_crawl_url(
    url: str,
    *,
    allowed_domains: list[str] | None = None,
    blocked_domains: list[str] | None = None,
    dev_mode: bool = False,
) -> UrlSafetyResult:
    raw = (url or "").strip()
    if not raw:
        return UrlSafetyResult(False, "URL 为空。")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return UrlSafetyResult(False, "仅允许 http/https URL。")
    if not parsed.hostname:
        return UrlSafetyResult(False, "URL 缺少域名。")
    domain = parsed.hostname.lower().strip(".")
    if _is_blocked_domain(domain, blocked_domains or []):
        return UrlSafetyResult(False, "该域名被安全策略禁止采集。", raw, domain)
    if not dev_mode and _is_private_or_local_host(domain):
        return UrlSafetyResult(False, "默认禁止采集 localhost、内网或私有 IP。", raw, domain)
    normalized_allowed = {item.lower().strip(".") for item in (allowed_domains or []) if item}
    if normalized_allowed and not any(domain == item or domain.endswith(f".{item}") for item in normalized_allowed):
        return UrlSafetyResult(False, "URL 不在本次采集允许域名内。", raw, domain)
    return UrlSafetyResult(True, "", raw, domain)


def same_registered_domain(url: str, seed_domain: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().strip(".")
    base = seed_domain.lower().strip(".")
    return bool(host and base and (host == base or host.endswith(f".{base}")))


def _is_blocked_domain(domain: str, extra_blocked: list[str]) -> bool:
    blocked = BLOCKED_DOMAINS | {item.lower().strip(".") for item in extra_blocked if item}
    if domain in blocked:
        return True
    return any(domain.endswith(suffix) for suffix in BLOCKED_HOST_SUFFIXES)


def _is_private_or_local_host(domain: str) -> bool:
    if domain in {"localhost", "localhost.localdomain"} or domain.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(domain)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local or address.is_reserved
