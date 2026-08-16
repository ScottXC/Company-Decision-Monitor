from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from cdm_desktop.public_api.models import ProviderError
from cdm_desktop.public_api.web_fetcher import SafeWebFetcher

CRAWLERGO_USER_AGENT = "CompanyDecisionMonitorBot/0.1.5"


@dataclass(frozen=True, slots=True)
class RobotsDecision:
    allowed: bool
    robots_url: str
    crawl_delay_seconds: float | None = None
    missing_robots: bool = False
    error_message: str = ""


class RobotsPolicy:
    def __init__(
        self,
        http: object | None = None,
        user_agent: str = CRAWLERGO_USER_AGENT,
        *,
        cache_ttl_seconds: int = 3600,
    ) -> None:
        self.http = http or SafeWebFetcher()
        self.user_agent = user_agent
        self.cache_ttl_seconds = max(60, cache_ttl_seconds)
        self._cache: dict[str, tuple[float, str | None, ProviderError | None]] = {}
        self._lock = threading.Lock()

    def can_fetch(
        self,
        url: str,
        *,
        allowed_domains: list[str] | None = None,
        blocked_domains: list[str] | None = None,
    ) -> RobotsDecision:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return RobotsDecision(False, "", error_message="URL 格式无效。")
        origin = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = urljoin(origin, "/robots.txt")
        text, error = self._robots_text(
            robots_url,
            allowed_domains=allowed_domains,
            blocked_domains=blocked_domains,
        )
        if error and error.state in {"unsafe_url", "response_too_large"}:
            return RobotsDecision(
                False,
                robots_url,
                error_message="robots.txt 的目标不安全，已停止自动采集。",
            )
        if error:
            return RobotsDecision(
                True,
                robots_url,
                missing_robots=True,
                error_message="未能读取 robots.txt，按至少一秒的低频率采集公开页面。",
            )
        return evaluate_robots_text(
            text or "",
            url,
            robots_url=robots_url,
            user_agent=self.user_agent,
        )

    def _robots_text(
        self,
        robots_url: str,
        *,
        allowed_domains: list[str] | None,
        blocked_domains: list[str] | None,
    ) -> tuple[str | None, ProviderError | None]:
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(robots_url)
            if cached and cached[0] > now:
                return cached[1], cached[2]
        text, error = self.http.get_text(
            "web_evidence",
            robots_url,
            allowed_domains=allowed_domains,
            blocked_domains=blocked_domains,
        )
        with self._lock:
            self._cache[robots_url] = (now + self.cache_ttl_seconds, text, error)
        return text, error


def evaluate_robots_text(
    robots_text: str,
    target_url: str,
    *,
    robots_url: str = "",
    user_agent: str = CRAWLERGO_USER_AGENT,
) -> RobotsDecision:
    parser = RobotFileParser()
    parser.set_url(robots_url)
    product_token = user_agent.split("/", 1)[0]
    parser.parse(_normalized_robots_lines(robots_text, user_agent, product_token))
    allowed = parser.can_fetch(product_token, target_url)
    delay = parser.crawl_delay(product_token) or parser.crawl_delay("*")
    if delay is None:
        delay = _parse_crawl_delay(robots_text, user_agent)
    return RobotsDecision(
        allowed=allowed,
        robots_url=robots_url,
        crawl_delay_seconds=float(delay) if delay is not None else None,
        missing_robots=False,
        error_message="" if allowed else "该页面不允许自动采集（robots.txt 已禁止）。",
    )


def _parse_crawl_delay(robots_text: str, user_agent: str) -> float | None:
    selected = False
    wildcard = False
    exact_delay: float | None = None
    wildcard_delay: float | None = None
    for raw_line in (robots_text or "").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.casefold()
        if key == "user-agent":
            selected = value.casefold() in {user_agent.casefold(), "companydecisionmonitorbot"}
            wildcard = value == "*"
        elif key == "crawl-delay":
            if not re.fullmatch(r"\d+(?:\.\d+)?", value):
                continue
            parsed = max(0.0, float(value))
            if selected:
                exact_delay = parsed
            elif wildcard:
                wildcard_delay = parsed
    return exact_delay if exact_delay is not None else wildcard_delay


def _normalized_robots_lines(
    robots_text: str,
    user_agent: str,
    product_token: str,
) -> list[str]:
    lines: list[str] = []
    for raw_line in (robots_text or "").splitlines():
        if ":" not in raw_line:
            lines.append(raw_line)
            continue
        key, value = raw_line.split(":", 1)
        if key.strip().casefold() == "user-agent" and value.strip().casefold() == user_agent.casefold():
            lines.append(f"User-agent: {product_token}")
        else:
            lines.append(raw_line)
    return lines
