from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from cdm_desktop.public_api.http_client import PublicHttpClient

CRAWLERGO_USER_AGENT = "CompanyDecisionMonitorBot/0.1.3"


@dataclass(frozen=True, slots=True)
class RobotsDecision:
    allowed: bool
    robots_url: str
    crawl_delay_seconds: float | None = None
    missing_robots: bool = False
    error_message: str = ""


class RobotsPolicy:
    def __init__(self, http: PublicHttpClient | None = None, user_agent: str = CRAWLERGO_USER_AGENT) -> None:
        self.http = http or PublicHttpClient(user_agent=user_agent)
        self.user_agent = user_agent

    def can_fetch(self, url: str) -> RobotsDecision:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return RobotsDecision(False, "", error_message="URL 格式无效。")
        robots_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", "/robots.txt")
        text, error = self.http.get_text("crawlergo_web_evidence", robots_url)
        if error:
            return RobotsDecision(
                True,
                robots_url,
                missing_robots=True,
                error_message="未能读取 robots.txt，按低频率采集公开页面。",
            )
        return evaluate_robots_text(text or "", url, robots_url=robots_url, user_agent=self.user_agent)


def evaluate_robots_text(
    robots_text: str,
    target_url: str,
    *,
    robots_url: str = "",
    user_agent: str = CRAWLERGO_USER_AGENT,
) -> RobotsDecision:
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse((robots_text or "").splitlines())
    allowed = parser.can_fetch(user_agent, target_url)
    delay = parser.crawl_delay(user_agent) or parser.crawl_delay("*")
    return RobotsDecision(
        allowed=allowed,
        robots_url=robots_url,
        crawl_delay_seconds=float(delay) if delay is not None else None,
        missing_robots=False,
        error_message="" if allowed else "该 URL 被 robots.txt 禁止访问，已跳过。",
    )
