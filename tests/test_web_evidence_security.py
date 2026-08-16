from __future__ import annotations

import socket

import httpx
import pytest

from cdm_desktop.public_api.crawl_safety import (
    BLOCKED_DOMAINS,
    crawl_skip_reason,
    validate_crawl_url,
)
from cdm_desktop.public_api.web_fetcher import SafeWebFetcher
from cdm_desktop.security.url_safety import (
    UnsafeUrlError,
    URLSafetyValidator,
    _validate_response_peer,
    safe_fetch_url,
)


def public_resolver(host: str, _port: object, *, type: int = 0):
    _ = type
    address = "93.184.216.34" if ":" not in host else "2606:2800:220:1:248:1893:25c8:1946"
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]


def private_resolver(_host: str, _port: object, *, type: int = 0):
    _ = type
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 443))]


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("https://example.com/path", True),
        ("http://example.com/path", True),
        ("file:///etc/passwd", False),
        ("ftp://example.com/file", False),
        ("javascript:alert(1)", False),
        ("data:text/plain,hello", False),
        ("http://localhost/", False),
        ("http://127.0.0.1/", False),
        ("http://[::1]/", False),
        ("http://10.1.2.3/", False),
        ("http://172.16.0.1/", False),
        ("http://192.168.1.1/", False),
        ("http://169.254.1.1/", False),
        ("http://[fc00::1]/", False),
        ("http://[fe80::1]/", False),
        ("http://169.254.169.254/latest/meta-data", False),
        ("http://100.100.100.200/latest/meta-data", False),
        ("http://[fd00:ec2::254]/latest/meta-data", False),
        ("https://user:password@example.com/", False),
        ("https://xueqiu.com/S/AAPL", False),
        ("https://XUEQIU.COM.:443/S/AAPL", False),
        ("https://news.xueqiu.com/S/AAPL", False),
    ],
)
def test_url_safety_allow_and_reject(url: str, allowed: bool) -> None:
    result = validate_crawl_url(url, resolver=public_resolver)
    assert result.allowed is allowed


def test_dns_private_ip_is_rejected() -> None:
    result = validate_crawl_url("https://internal.example/", resolver=private_resolver)
    assert not result.allowed
    assert "内网" in result.reason


def test_redirect_to_private_ip_is_revalidated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"}, request=request)

    with pytest.raises(UnsafeUrlError):
        safe_fetch_url(
            "https://example.com/start",
            resolver=public_resolver,
            transport=httpx.MockTransport(handler),
        )


def test_redirect_to_blocked_or_out_of_scope_domain_stops_before_second_get() -> None:
    for location in (
        "https://xueqiu.com/S/AAPL",
        "https://other.example/public",
    ):
        seen: list[str] = []

        def handler(
            request: httpx.Request,
            *,
            seen: list[str] = seen,
            location: str = location,
        ) -> httpx.Response:
            seen.append(str(request.url))
            return httpx.Response(302, headers={"Location": location}, request=request)

        fetcher = SafeWebFetcher(
            resolver=public_resolver,
            transport=httpx.MockTransport(handler),
        )
        response, error = fetcher.fetch(
            "https://example.com/start",
            allowed_domains=["example.com"],
        )

        assert response is None
        assert error is not None
        assert error.state == "unsafe_url"
        assert seen == ["https://example.com/start"]


def test_actual_peer_ip_is_checked_against_dns_rebinding() -> None:
    class PrivateNetworkStream:
        def get_extra_info(self, name: str):
            assert name == "server_addr"
            return ("192.168.10.20", 443)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="public response",
            request=request,
            extensions={"network_stream": PrivateNetworkStream()},
        )

    with pytest.raises(UnsafeUrlError):
        safe_fetch_url(
            "https://example.com/",
            resolver=public_resolver,
            transport=httpx.MockTransport(handler),
        )


def test_real_transport_fails_closed_when_peer_ip_is_unavailable() -> None:
    request = httpx.Request("GET", "https://example.com/")
    response = httpx.Response(200, request=request)

    with pytest.raises(UnsafeUrlError, match="实际连接 IP"):
        _validate_response_peer(
            response,
            URLSafetyValidator(resolver=public_resolver),
            required=True,
        )


def test_web_fetcher_sends_no_cookie_token_or_impersonation_headers() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        captured.update({key.casefold(): value for key, value in request.headers.items()})
        return httpx.Response(
            200,
            text="<html><body>ok</body></html>",
            headers={"Content-Type": "text/html; charset=utf-8"},
            request=request,
        )

    fetcher = SafeWebFetcher(
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    response, error = fetcher.fetch("https://example.com/")

    assert error is None
    assert response is not None
    assert captured["user-agent"] == "CompanyDecisionMonitorBot/0.1.5"
    assert "cookie" not in captured
    assert "authorization" not in captured
    assert "xq_a_token" not in " ".join(captured.values()).casefold()


def test_caller_supplied_authentication_headers_are_ignored() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update({key.casefold(): value for key, value in request.headers.items()})
        return httpx.Response(
            200,
            text="User-agent: *\nAllow: /",
            headers={"Content-Type": "text/plain"},
            request=request,
        )

    fetcher = SafeWebFetcher(
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    text, error = fetcher.get_text(
        "web_evidence",
        "https://example.com/robots.txt",
        headers={
            "Cookie": "session=secret",
            "Authorization": "Bearer secret",
            "xq_a_token": "secret",
        },
        allowed_domains=["example.com"],
    )

    assert error is None
    assert text
    assert "cookie" not in captured
    assert "authorization" not in captured
    assert "xq_a_token" not in captured


def test_pdf_response_body_is_not_downloaded_or_decoded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"%PDF-secret-body-that-must-not-be-read",
            headers={"Content-Type": "application/pdf", "Content-Length": "999999"},
            request=request,
        )

    fetched = safe_fetch_url(
        "https://example.com/report",
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    assert fetched.content == b""


def test_scope_filters_login_binary_calendar_and_xueqiu() -> None:
    assert "xueqiu.com" in BLOCKED_DOMAINS
    assert crawl_skip_reason("https://example.com/login")
    assert crawl_skip_reason("https://example.com/download/file.zip")
    assert crawl_skip_reason("https://example.com/calendar?page=999")
    assert not crawl_skip_reason("https://example.com/investors")
