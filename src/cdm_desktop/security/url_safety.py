from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

import httpx


class UnsafeUrlError(ValueError):
    pass


class FetchTooLargeError(ValueError):
    pass


@dataclass(frozen=True)
class FetchedUrl:
    url: str
    final_url: str
    content_type: str
    content: bytes
    status_code: int


BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain"}
METADATA_IP = ipaddress.ip_address("169.254.169.254")
ALLOWED_SCHEMES = {"http", "https"}


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme and parsed.netloc:
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        return urlunparse((scheme, netloc, parsed.path or "/", "", parsed.query, ""))
    return url.strip()


def validate_url(url: str, *, resolver: object | None = None) -> str:
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeUrlError("仅允许 http 或 https URL")
    if not parsed.hostname:
        raise UnsafeUrlError("URL 缺少主机名")

    hostname = parsed.hostname.lower().rstrip(".")
    if hostname in BLOCKED_HOSTNAMES or hostname.endswith(".localhost"):
        raise UnsafeUrlError("不允许访问 localhost")

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        _validate_resolved_hostname(hostname, resolver=resolver)
    else:
        _validate_ip(ip)

    return normalized


def safe_fetch_url(url: str, *, timeout_seconds: int = 15, max_bytes: int = 5_000_000) -> FetchedUrl:
    checked_url = validate_url(url)
    timeout = httpx.Timeout(timeout_seconds, connect=timeout_seconds)
    with httpx.Client(follow_redirects=True, timeout=timeout, trust_env=False) as client, client.stream(
        "GET",
        checked_url,
        headers={"User-Agent": "CompanyDecisionMonitor/0.1"},
    ) as response:
        response.raise_for_status()
        final_url = validate_url(str(response.url))
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > max_bytes:
            raise FetchTooLargeError(f"响应内容超过限制: {max_bytes} bytes")

        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > max_bytes:
                raise FetchTooLargeError(f"响应内容超过限制: {max_bytes} bytes")
            chunks.append(chunk)

        return FetchedUrl(
            url=checked_url,
            final_url=final_url,
            content_type=response.headers.get("content-type", "application/octet-stream"),
            content=b"".join(chunks),
            status_code=response.status_code,
        )


def _validate_resolved_hostname(hostname: str, *, resolver: object | None = None) -> None:
    resolve = resolver or socket.getaddrinfo
    try:
        addresses = resolve(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"无法解析主机名: {hostname}") from exc

    if not addresses:
        raise UnsafeUrlError(f"无法解析主机名: {hostname}")

    for address in addresses:
        ip_text = address[4][0]
        _validate_ip(ipaddress.ip_address(ip_text))


def _validate_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if ip == METADATA_IP:
        raise UnsafeUrlError("不允许访问云 metadata 服务地址")
    if ip.is_loopback:
        raise UnsafeUrlError("不允许访问 loopback 地址")
    if ip.is_private:
        raise UnsafeUrlError("不允许访问内网地址")
    if ip.is_link_local:
        raise UnsafeUrlError("不允许访问 link-local 地址")
    if ip.is_unspecified:
        raise UnsafeUrlError("不允许访问未指定地址")
    if ip.is_multicast:
        raise UnsafeUrlError("不允许访问 multicast 地址")
