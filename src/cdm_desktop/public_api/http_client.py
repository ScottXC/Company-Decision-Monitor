from __future__ import annotations

import time
from typing import Any

import httpx

from cdm_desktop.public_api.models import ProviderError


class PublicHttpClient:
    def __init__(
        self,
        *,
        user_agent: str = "CompanyDecisionMonitor/0.1.3",
        timeout_seconds: float = 15.0,
        retry_count: int = 2,
    ) -> None:
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.retry_count = retry_count

    def get_json(
        self,
        provider_id: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        auth: tuple[str, str] | None = None,
    ) -> tuple[Any | None, ProviderError | None]:
        response, error = self._get(provider_id, url, params=params, headers=headers, auth=auth)
        if error:
            return None, error
        assert response is not None
        try:
            return response.json(), None
        except ValueError:
            return None, ProviderError(
                provider_id=provider_id,
                state="parse_error",
                message="JSON 解析失败，provider 返回格式异常。",
                retryable=False,
            )

    def get_text(
        self,
        provider_id: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[str | None, ProviderError | None]:
        response, error = self._get(provider_id, url, params=params, headers=headers)
        if error:
            return None, error
        assert response is not None
        return response.text, None

    def _get(
        self,
        provider_id: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        auth: tuple[str, str] | None = None,
    ) -> tuple[httpx.Response | None, ProviderError | None]:
        merged_headers = {"User-Agent": self.user_agent, **(headers or {})}
        last_error: ProviderError | None = None
        for attempt in range(self.retry_count + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                    response = client.get(
                        url,
                        params=params,
                        headers=merged_headers,
                        auth=auth,
                    )
            except httpx.TimeoutException:
                last_error = ProviderError(
                    provider_id,
                    "network_timeout",
                    "网络请求超时，请检查网络连接后重试。",
                    retryable=True,
                )
            except httpx.RequestError:
                last_error = ProviderError(
                    provider_id,
                    "dns_failure",
                    "网络不可用或 DNS 解析失败，请检查网络连接。",
                    retryable=True,
                )
            else:
                if response.status_code == 401:
                    return None, ProviderError(
                        provider_id,
                        "invalid_key",
                        "API key 无效或认证失败，请检查设置页配置。",
                        401,
                    )
                if response.status_code == 403:
                    return None, ProviderError(
                        provider_id,
                        "invalid_key",
                        "请求被拒绝，可能是 key 权限、User-Agent 或访问频率问题。",
                        403,
                    )
                if response.status_code == 429:
                    last_error = ProviderError(
                        provider_id,
                        "rate_limited",
                        "已达到 provider 访问频率或免费层额度限制，请稍后重试。",
                        429,
                        retryable=True,
                    )
                elif response.status_code >= 400:
                    return None, ProviderError(
                        provider_id,
                        "http_error",
                        f"外部服务返回错误状态码 {response.status_code}。",
                        response.status_code,
                        retryable=response.status_code >= 500,
                    )
                else:
                    return response, None
            if attempt < self.retry_count:
                time.sleep(0.3 * (attempt + 1))
        return None, last_error
