from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from cdm_desktop.security.url_safety import UnsafeUrlError, URLSafetyValidator

BLOCKED_DOMAINS = {
    "xueqiu.com",
    "www.xueqiu.com",
    "mp.weixin.qq.com",
    "weixin.qq.com",
    "facebook.com",
    "www.facebook.com",
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
    "weibo.com",
    "www.weibo.com",
}

BLOCKED_HOST_SUFFIXES = tuple(f".{domain}" for domain in BLOCKED_DOMAINS)

TRACKING_QUERY_PREFIXES = ("utm_", "pk_", "ga_")
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "dclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "source",
    "campaign",
}
SKIPPED_PATH_MARKERS = (
    "/login",
    "/signin",
    "/sign-in",
    "/account",
    "/user/",
    "/cart",
    "/checkout",
    "/search",
    "/wp-login",
    "/admin",
)
BINARY_EXTENSIONS = {
    ".zip",
    ".7z",
    ".rar",
    ".exe",
    ".msi",
    ".dmg",
    ".pkg",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".mp3",
    ".mp4",
    ".avi",
    ".mov",
}


@dataclass(frozen=True, slots=True)
class UrlSafetyResult:
    allowed: bool
    reason: str = ""
    normalized_url: str = ""
    domain: str = ""
    resolved_ips: tuple[str, ...] = ()


def validate_crawl_url(
    url: str,
    *,
    allowed_domains: list[str] | None = None,
    blocked_domains: list[str] | None = None,
    dev_mode: bool = False,
    resolver: Any | None = None,
) -> UrlSafetyResult:
    raw = (url or "").strip()
    if not raw:
        return UrlSafetyResult(False, "URL 为空。")
    try:
        validated = URLSafetyValidator(
            resolver=resolver,
            allow_localhost_for_dev=dev_mode,
        ).validate(raw)
    except UnsafeUrlError as exc:
        return UrlSafetyResult(False, str(exc))

    domain = validated.hostname
    if _is_blocked_domain(domain, blocked_domains or []):
        return UrlSafetyResult(
            False,
            "该域名被安全策略禁止采集。",
            validated.url,
            domain,
            validated.resolved_ips,
        )
    normalized_allowed = {
        item.casefold().strip(".").removeprefix("www.")
        for item in (allowed_domains or [])
        if item
    }
    compared_domain = domain.removeprefix("www.")
    if normalized_allowed and not any(
        compared_domain == item or compared_domain.endswith(f".{item}")
        for item in normalized_allowed
    ):
        return UrlSafetyResult(
            False,
            "URL 不在本次采集允许域名内。",
            validated.url,
            domain,
            validated.resolved_ips,
        )
    normalized = canonicalize_crawl_url(validated.url)
    return UrlSafetyResult(True, "", normalized, domain, validated.resolved_ips)


def canonicalize_crawl_url(url: str) -> str:
    parsed = urlsplit(url)
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in TRACKING_QUERY_KEYS
        and not key.casefold().startswith(TRACKING_QUERY_PREFIXES)
    ]
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            parsed.netloc.casefold(),
            path,
            urlencode(sorted(filtered_query)),
            "",
        )
    )


def crawl_skip_reason(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path.casefold()
    if any(marker in path for marker in SKIPPED_PATH_MARKERS):
        return "登录、账号、搜索、购物车或管理页面不在采集范围内。"
    suffix = "." + path.rsplit(".", 1)[-1] if "." in path.rsplit("/", 1)[-1] else ""
    if suffix in BINARY_EXTENSIONS:
        return "该二进制文件类型不在本版本采集范围内。"
    if _looks_like_unbounded_calendar(parsed.path, parsed.query):
        return "可能为无限日历或重复分页 URL，已跳过。"
    if len(parse_qsl(parsed.query, keep_blank_values=True)) > 8:
        return "查询参数过多，疑似跟踪或无限分页 URL。"
    return ""


def is_pdf_url(url: str) -> bool:
    return urlsplit(url).path.casefold().endswith(".pdf")


def same_registered_domain(url: str, seed_domain: str) -> bool:
    host = (urlsplit(url).hostname or "").casefold().strip(".")
    base = seed_domain.casefold().strip(".")
    host = host.removeprefix("www.")
    base = base.removeprefix("www.")
    return bool(host and base and (host == base or host.endswith(f".{base}")))


def _is_blocked_domain(domain: str, extra_blocked: list[str]) -> bool:
    blocked = BLOCKED_DOMAINS | {item.casefold().strip(".") for item in extra_blocked if item}
    if domain in blocked:
        return True
    suffixes = BLOCKED_HOST_SUFFIXES + tuple(f".{item}" for item in blocked)
    return any(domain.endswith(suffix) for suffix in suffixes)


def _looks_like_unbounded_calendar(path: str, query: str) -> bool:
    value = f"{path}?{query}".casefold()
    calendar_marker = any(marker in value for marker in ("calendar", "event-calendar", "date="))
    paging_marker = any(marker in value for marker in ("page=", "offset=", "start="))
    return calendar_marker and paging_marker
