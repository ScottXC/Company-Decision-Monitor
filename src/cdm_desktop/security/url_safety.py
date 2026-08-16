from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

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


@dataclass(frozen=True)
class ValidatedUrl:
    url: str
    hostname: str
    resolved_ips: tuple[str, ...]


Resolver = Callable[..., list[Any]]

BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata",
    "metadata.google.internal",
    "instance-data",
    "instance-data.ec2.internal",
}
METADATA_IPS = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("100.100.100.200"),
    ipaddress.ip_address("fd00:ec2::254"),
}
ALLOWED_SCHEMES = {"http", "https"}


class URLSafetyValidator:
    def __init__(
        self,
        *,
        resolver: Resolver | None = None,
        allow_localhost_for_dev: bool = False,
        allowed_domains: Iterable[str] | None = None,
        blocked_domains: Iterable[str] | None = None,
    ) -> None:
        self.resolver = resolver or socket.getaddrinfo
        self.allow_localhost_for_dev = allow_localhost_for_dev
        self.allowed_domains = _normalized_domains(allowed_domains)
        self.blocked_domains = _normalized_domains(blocked_domains)

    def validate(self, url: str) -> ValidatedUrl:
        raw_parsed = urlsplit((url or "").strip())
        if raw_parsed.username is not None or raw_parsed.password is not None:
            raise UnsafeUrlError("URL 不允许包含用户名或密码")
        normalized = normalize_url(url)
        parsed = urlsplit(normalized)
        if parsed.scheme not in ALLOWED_SCHEMES:
            raise UnsafeUrlError("仅允许 http 或 https URL")
        if not parsed.hostname:
            raise UnsafeUrlError("URL 缺少主机名")
        hostname = parsed.hostname.casefold().rstrip(".")
        if not self.allow_localhost_for_dev and (
            hostname in BLOCKED_HOSTNAMES or hostname.endswith(".localhost")
        ):
            raise UnsafeUrlError("不允许访问 localhost 或 metadata 主机")
        compared_hostname = _scope_hostname(hostname)
        if any(
            compared_hostname == blocked
            or compared_hostname.endswith(f".{blocked}")
            for blocked in self.blocked_domains
        ):
            raise UnsafeUrlError("该域名被安全策略禁止采集")
        if self.allowed_domains and not any(
            compared_hostname == allowed
            or compared_hostname.endswith(f".{allowed}")
            for allowed in self.allowed_domains
        ):
            raise UnsafeUrlError("URL 不在本次采集允许域名内")

        try:
            literal = ipaddress.ip_address(hostname)
        except ValueError:
            resolved = self._resolve(hostname)
        else:
            self._validate_ip(literal)
            resolved = (str(literal),)
        return ValidatedUrl(normalized, hostname, resolved)

    def validate_peer_ip(self, ip_text: str) -> None:
        try:
            address = ipaddress.ip_address(ip_text.split("%", 1)[0])
        except ValueError as exc:
            raise UnsafeUrlError("无法验证实际连接 IP") from exc
        self._validate_ip(address)

    def _resolve(self, hostname: str) -> tuple[str, ...]:
        try:
            addresses = self.resolver(hostname, None, type=socket.SOCK_STREAM)
        except (OSError, socket.gaierror) as exc:
            raise UnsafeUrlError(f"无法解析主机名: {hostname}") from exc
        if not addresses:
            raise UnsafeUrlError(f"无法解析主机名: {hostname}")

        resolved: list[str] = []
        for address in addresses:
            try:
                ip_text = str(address[4][0]).split("%", 1)[0]
                ip = ipaddress.ip_address(ip_text)
            except (IndexError, TypeError, ValueError) as exc:
                raise UnsafeUrlError(f"DNS 返回无法验证的地址: {hostname}") from exc
            self._validate_ip(ip)
            if str(ip) not in resolved:
                resolved.append(str(ip))
        return tuple(resolved)

    def _validate_ip(self, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        if self.allow_localhost_for_dev and ip.is_loopback:
            return
        if ip in METADATA_IPS:
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
        if ip.is_reserved or not ip.is_global:
            raise UnsafeUrlError("不允许访问非公网地址")


def normalize_url(url: str) -> str:
    raw = (url or "").strip()
    parsed = urlsplit(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw
    scheme = parsed.scheme.casefold()
    hostname = (parsed.hostname or "").casefold().rstrip(".")
    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeUrlError("URL 端口无效") from exc
    host_text = f"[{hostname}]" if ":" in hostname else hostname
    netloc = f"{host_text}:{port}" if port is not None else host_text
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def validate_url(
    url: str,
    *,
    resolver: Resolver | None = None,
    allow_localhost_for_dev: bool = False,
    allowed_domains: Iterable[str] | None = None,
    blocked_domains: Iterable[str] | None = None,
) -> str:
    return URLSafetyValidator(
        resolver=resolver,
        allow_localhost_for_dev=allow_localhost_for_dev,
        allowed_domains=allowed_domains,
        blocked_domains=blocked_domains,
    ).validate(url).url


def safe_fetch_url(
    url: str,
    *,
    timeout_seconds: int = 15,
    max_bytes: int = 5_000_000,
    max_redirects: int = 5,
    user_agent: str = "CompanyDecisionMonitorBot/0.1.5",
    resolver: Resolver | None = None,
    transport: httpx.BaseTransport | None = None,
    allow_localhost_for_dev: bool = False,
    allowed_domains: Iterable[str] | None = None,
    blocked_domains: Iterable[str] | None = None,
) -> FetchedUrl:
    validator = URLSafetyValidator(
        resolver=resolver,
        allow_localhost_for_dev=allow_localhost_for_dev,
        allowed_domains=allowed_domains,
        blocked_domains=blocked_domains,
    )
    initial = validator.validate(url).url
    current = initial
    timeout = httpx.Timeout(timeout_seconds, connect=timeout_seconds)
    with httpx.Client(
        follow_redirects=False,
        timeout=timeout,
        trust_env=False,
        transport=transport,
    ) as client:
        for redirect_count in range(max_redirects + 1):
            checked = validator.validate(current).url
            request = client.build_request(
                "GET",
                checked,
                headers={
                    "User-Agent": user_agent,
                    "Accept": "text/html,application/xhtml+xml,text/plain,application/pdf;q=0.5",
                },
            )
            response = client.send(request, stream=True)
            try:
                _validate_response_peer(
                    response,
                    validator,
                    required=transport is None,
                )
                if response.is_redirect:
                    location = response.headers.get("location", "").strip()
                    if not location:
                        raise UnsafeUrlError("重定向响应缺少目标地址")
                    if redirect_count >= max_redirects:
                        raise UnsafeUrlError("重定向次数超过限制")
                    current = validator.validate(urljoin(checked, location)).url
                    continue
                response.raise_for_status()
                response_content_type = response.headers.get(
                    "content-type", "application/octet-stream"
                )
                if "application/pdf" in response_content_type.casefold():
                    return FetchedUrl(
                        url=initial,
                        final_url=validator.validate(str(response.url)).url,
                        content_type=response_content_type,
                        content=b"",
                        status_code=response.status_code,
                    )
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        declared_length = int(content_length)
                    except ValueError:
                        declared_length = 0
                    if declared_length > max_bytes:
                        raise FetchTooLargeError(f"响应内容超过限制: {max_bytes} bytes")

                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise FetchTooLargeError(f"响应内容超过限制: {max_bytes} bytes")
                    chunks.append(chunk)
                return FetchedUrl(
                    url=initial,
                    final_url=validator.validate(str(response.url)).url,
                    content_type=response_content_type,
                    content=b"".join(chunks),
                    status_code=response.status_code,
                )
            finally:
                response.close()
    raise UnsafeUrlError("无法完成安全 URL 请求")


def _validate_response_peer(
    response: httpx.Response,
    validator: URLSafetyValidator,
    *,
    required: bool,
) -> None:
    stream = response.extensions.get("network_stream")
    if stream is None or not hasattr(stream, "get_extra_info"):
        if required:
            raise UnsafeUrlError("无法验证实际连接 IP，已安全终止请求")
        return
    try:
        server_addr = stream.get_extra_info("server_addr")
    except (OSError, RuntimeError) as exc:
        if required:
            raise UnsafeUrlError("无法验证实际连接 IP，已安全终止请求") from exc
        return
    if isinstance(server_addr, (tuple, list)) and server_addr:
        validator.validate_peer_ip(str(server_addr[0]))
        return
    if required:
        raise UnsafeUrlError("无法验证实际连接 IP，已安全终止请求")


def _normalized_domains(values: Iterable[str] | None) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values or ():
        hostname = _scope_hostname(str(value))
        if hostname and hostname not in normalized:
            normalized.append(hostname)
    return tuple(normalized)


def _scope_hostname(value: str) -> str:
    return value.casefold().strip().strip(".").removeprefix("www.")
