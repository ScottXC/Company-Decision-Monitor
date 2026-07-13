from __future__ import annotations

import re
from html import unescape
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from cdm_desktop.public_api.web_evidence_models import WebEvidenceItem, utc_now_iso

SNIPPET_LIMIT = 300
PREVIEW_LIMIT = 800


def extract_web_evidence(
    html: str,
    *,
    source_url: str,
    final_url: str | None = None,
    company_name: str = "",
    crawl_depth: int = 0,
    robots_allowed: bool = True,
    from_cache: bool = False,
) -> WebEvidenceItem:
    final = final_url or source_url
    soup = BeautifulSoup(html or "", "lxml")
    title = _first_content(
        _meta(soup, "og:title"),
        _title(soup),
        _first_text(soup, "h1"),
    )
    description = _first_content(
        _meta(soup, "description"),
        _meta(soup, "og:description"),
        _json_ld_value(soup, "description"),
    )
    published = _first_content(
        _meta(soup, "article:published_time"),
        _json_ld_value(soup, "datePublished"),
    )
    language = (soup.html.get("lang", "") if soup.html else "") or ""
    text = _main_text(soup)
    snippet_source = description or text
    domain = (urlparse(final).hostname or "").lower()
    now = utc_now_iso()
    return WebEvidenceItem(
        id=WebEvidenceItem.create_id(final),
        company_name=company_name,
        source_url=source_url,
        final_url=final,
        domain=domain,
        title=_clean(title),
        description=_clean(description),
        content_snippet=_truncate(_clean(snippet_source), SNIPPET_LIMIT),
        extracted_text_preview=_truncate(_clean(text), PREVIEW_LIMIT),
        content_type=classify_content(final, title, description),
        language=language,
        published_at=published,
        discovered_at=now,
        crawled_at=now,
        crawl_depth=crawl_depth,
        robots_allowed=robots_allowed,
        status="ok",
        open_url=final,
        from_cache=from_cache,
    )


def classify_content(url: str, title: str = "", description: str = "") -> str:
    haystack = " ".join([urlparse(url).path, title or "", description or ""]).casefold()
    rules = [
        ("investor_relations", ("investor", "/ir", "investor relations", "shareholder")),
        ("press_release", ("press-release", "press release", "/press/", "news release")),
        ("announcement", ("announcement", "announcements", "公告", "disclosure")),
        ("blog", ("blog", "/blog/")),
        ("news", ("news", "/media/", "media center")),
        ("product", ("product", "products", "solution")),
        ("careers", ("career", "jobs", "招聘")),
        ("official_site", ("about", "company", "overview")),
    ]
    for content_type, needles in rules:
        if any(needle in haystack for needle in needles):
            return content_type
    return "other"


def _title(soup: BeautifulSoup) -> str:
    return soup.title.get_text(" ", strip=True) if soup.title else ""


def _meta(soup: BeautifulSoup, name: str) -> str:
    tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
    if not tag:
        return ""
    return str(tag.get("content") or "")


def _json_ld_value(soup: BeautifulSoup, key: str) -> str:
    pattern = re.compile(rf'"{re.escape(key)}"\s*:\s*"([^"]+)"')
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.string or script.get_text(" ", strip=True)
        match = pattern.search(text or "")
        if match:
            return unescape(match.group(1))
    return ""


def _first_text(soup: BeautifulSoup, selector: str) -> str:
    tag = soup.select_one(selector)
    return tag.get_text(" ", strip=True) if tag else ""


def _main_text(soup: BeautifulSoup) -> str:
    for unwanted in soup(["script", "style", "noscript", "svg", "iframe"]):
        unwanted.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    return root.get_text(" ", strip=True)


def _first_content(*values: str) -> str:
    for value in values:
        if _clean(value):
            return value
    return ""


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value or "")).strip()


def _truncate(value: str, limit: int) -> str:
    cleaned = _clean(value)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 1)].rstrip() + "…"
