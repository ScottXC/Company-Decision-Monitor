from __future__ import annotations

import hashlib
import json
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from bs4.element import Tag

from cdm_desktop.public_api.crawl_safety import canonicalize_crawl_url
from cdm_desktop.public_api.web_evidence_models import WebEvidenceItem, utc_now_iso

SNIPPET_LIMIT = 300
PREVIEW_LIMIT = 800
DEFAULT_TEXT_LIMIT = 100_000
MAX_LINKS = 250
MAX_JSON_LD_ITEMS = 50

SUPPORTED_JSON_LD_TYPES = {
    "organization",
    "corporation",
    "newsarticle",
    "article",
    "pressrelease",
    "webpage",
    "breadcrumblist",
}
ORGANIZATION_FIELDS = {
    "name",
    "alternateName",
    "legalName",
    "url",
    "logo",
    "address",
    "telephone",
    "email",
    "foundingDate",
    "sameAs",
}
JSON_LD_ALLOWED_KEYS = {
    "@id",
    "@type",
    "name",
    "alternateName",
    "legalName",
    "headline",
    "description",
    "url",
    "logo",
    "image",
    "address",
    "streetAddress",
    "addressLocality",
    "addressRegion",
    "postalCode",
    "addressCountry",
    "telephone",
    "email",
    "foundingDate",
    "sameAs",
    "datePublished",
    "dateModified",
    "author",
    "publisher",
    "mainEntityOfPage",
    "itemListElement",
    "item",
    "position",
}


def extract_web_evidence(
    html: str,
    *,
    source_url: str,
    final_url: str | None = None,
    company_id: str = "",
    company_name: str = "",
    crawl_depth: int = 0,
    robots_allowed: bool = True,
    from_cache: bool = False,
    is_official_domain: bool = False,
    max_content_chars: int = DEFAULT_TEXT_LIMIT,
) -> WebEvidenceItem:
    final = final_url or source_url
    soup = BeautifulSoup(html or "", "lxml")
    json_ld = _json_ld_items(soup)
    structured = _structured_data(json_ld)

    title_tag = _title(soup)
    meta_description = _meta(soup, "description")
    og_title = _meta(soup, "og:title")
    og_description = _meta(soup, "og:description")
    h1 = _first_text(soup, "h1")
    title = _first_content(og_title, title_tag, h1, _json_ld_value(json_ld, "headline"))
    description = _first_content(
        meta_description,
        og_description,
        _json_ld_value(json_ld, "description"),
    )
    published = _first_content(
        _meta(soup, "article:published_time"),
        _meta(soup, "date"),
        _json_ld_value(json_ld, "datePublished"),
    )
    modified = _first_content(
        _meta(soup, "article:modified_time"),
        _json_ld_value(json_ld, "dateModified"),
    )
    author = _first_content(
        _meta(soup, "author"),
        _author_value(json_ld),
    )
    site_name = _first_content(
        _meta(soup, "og:site_name"),
        _json_ld_value(json_ld, "publisher.name"),
    )
    language = _clean(soup.html.get("lang", "") if soup.html else "")
    canonical = _canonical_url(soup, final)
    headings = _headings(soup)
    links = _links(soup, final)
    cleaned_text = _main_text(soup, max_content_chars=max_content_chars)
    content_type = classify_content(
        final,
        title,
        description,
        json_ld=json_ld,
        is_official_domain=is_official_domain,
    )
    display_mode = "full_cleaned_text" if is_official_domain else "excerpt_only"
    snippet_source = description or cleaned_text
    snippet = _truncate(snippet_source, SNIPPET_LIMIT)
    preview = _truncate(cleaned_text, PREVIEW_LIMIT)
    stored_text = cleaned_text if display_mode == "full_cleaned_text" else ""
    domain = (urlsplit(final).hostname or "").casefold()
    now = utc_now_iso()
    content_hash = hashlib.sha256(
        (cleaned_text or description or title or canonical).encode("utf-8")
    ).hexdigest()
    return WebEvidenceItem(
        id=WebEvidenceItem.create_id(canonical, company_id),
        company_id=company_id,
        company_name=company_name,
        source_url=source_url,
        final_url=final,
        canonical_url=canonical,
        domain=domain,
        title=_clean(title),
        description=_clean(description),
        meta_description=_clean(meta_description),
        og_title=_clean(og_title),
        og_description=_clean(og_description),
        h1=_clean(h1),
        cleaned_text=stored_text,
        content_snippet=snippet,
        extracted_text_preview=preview,
        content_type=content_type,
        language=language,
        site_name=_clean(site_name),
        author=_clean(author),
        published_at=_clean(published),
        modified_at=_clean(modified),
        discovered_at=now,
        crawled_at=now,
        robots_allowed=robots_allowed,
        is_official_domain=is_official_domain,
        display_mode=display_mode,
        provider="web_evidence",
        content_hash=content_hash,
        from_cache=from_cache,
        status="ok",
        headings=headings,
        links=links,
        json_ld=json_ld,
        structured_data=structured,
        crawl_depth=crawl_depth,
        open_url=final,
    )


def extract_pdf_evidence(
    *,
    source_url: str,
    final_url: str | None = None,
    company_id: str = "",
    company_name: str = "",
    title: str = "",
    crawl_depth: int = 0,
    robots_allowed: bool = True,
    is_official_domain: bool = False,
) -> WebEvidenceItem:
    final = final_url or source_url
    canonical = canonicalize_crawl_url(final)
    inferred_title = title or _pdf_title(final)
    content_type = classify_content(
        final,
        inferred_title,
        is_official_domain=is_official_domain,
        is_pdf=True,
    )
    now = utc_now_iso()
    return WebEvidenceItem(
        id=WebEvidenceItem.create_id(canonical, company_id),
        company_id=company_id,
        company_name=company_name,
        source_url=source_url,
        final_url=final,
        canonical_url=canonical,
        domain=(urlsplit(final).hostname or "").casefold(),
        title=inferred_title,
        content_snippet="PDF 正文未在此版本下载或解析，请在系统浏览器中查看原文。",
        extracted_text_preview="",
        content_type=content_type,
        discovered_at=now,
        crawled_at=now,
        robots_allowed=robots_allowed,
        is_official_domain=is_official_domain,
        display_mode="metadata_only",
        provider="web_evidence",
        content_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        status="ok",
        crawl_depth=crawl_depth,
        open_url=final,
    )


def classify_content(
    url: str,
    title: str = "",
    description: str = "",
    *,
    json_ld: list[dict[str, Any]] | None = None,
    is_official_domain: bool = False,
    is_pdf: bool = False,
) -> str:
    path = urlsplit(url).path.casefold()
    haystack = " ".join([path, title or "", description or ""]).casefold()
    schema_types = {
        item_type.casefold()
        for item in (json_ld or [])
        for item_type in _schema_types(item)
    }
    if any(needle in haystack for needle in ("annual-report", "annual report", "年报")):
        return "annual_report"
    if is_pdf or path.endswith(".pdf"):
        if any(needle in haystack for needle in ("annual", "年报")):
            return "annual_report"
        return "financial_report"
    if "pressrelease" in schema_types or any(
        needle in haystack
        for needle in ("press-release", "press release", "/press/", "news release")
    ):
        return "press_release"
    if any(
        needle in haystack
        for needle in ("investor-relations", "investor relations", "/investor", "/investors", "/ir/")
    ):
        return "investor_relations"
    if any(needle in haystack for needle in ("announcement", "announcements", "公告", "disclosure")):
        return "announcement"
    if any(needle in haystack for needle in ("financial", "results", "earnings", "reports")):
        return "financial_report"
    if any(needle in haystack for needle in ("/blog", "official blog")):
        return "official_blog" if is_official_domain else "other"
    if any(needle in haystack for needle in ("career", "jobs", "招聘")):
        return "careers"
    if any(needle in haystack for needle in ("product", "products", "solution")):
        return "product"
    if schema_types & {"newsarticle", "article"} or any(
        needle in haystack for needle in ("/news", "/media/", "media center")
    ):
        return "official_news" if is_official_domain else "third_party_news"
    if is_official_domain and path.strip("/") in {"", "home", "about", "company", "overview"}:
        return "company_homepage"
    return "other"


def _title(soup: BeautifulSoup) -> str:
    return soup.title.get_text(" ", strip=True) if soup.title else ""


def _meta(soup: BeautifulSoup, name: str) -> str:
    folded = name.casefold()
    for tag in soup.find_all("meta"):
        key = str(tag.get("name") or tag.get("property") or "").casefold()
        if key == folded:
            return str(tag.get("content") or "")
    return ""


def _json_ld_items(soup: BeautifulSoup) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        raw = script.string or script.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(unescape(raw).strip())
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        for item in _walk_json_ld(payload):
            if _schema_types(item) & SUPPORTED_JSON_LD_TYPES:
                sanitized = _sanitize_json_ld(item)
                if isinstance(sanitized, dict):
                    items.append(sanitized)
                if len(items) >= MAX_JSON_LD_ITEMS:
                    return items
    return items


def _walk_json_ld(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, list):
        for child in value:
            found.extend(_walk_json_ld(child))
    elif isinstance(value, dict):
        graph = value.get("@graph")
        if graph is not None:
            found.extend(_walk_json_ld(graph))
        if "@type" in value:
            found.append(value)
    return found


def _sanitize_json_ld(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return None
    if isinstance(value, dict):
        return {
            str(key): sanitized
            for key, child in value.items()
            if key in JSON_LD_ALLOWED_KEYS
            and (sanitized := _sanitize_json_ld(child, depth=depth + 1))
            not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [
            sanitized
            for child in value[:50]
            if (sanitized := _sanitize_json_ld(child, depth=depth + 1))
            not in (None, "", [], {})
        ]
    if isinstance(value, str):
        return _clean(value)[:2_000]
    if isinstance(value, (int, float, bool)):
        return value
    return None


def _schema_types(item: dict[str, Any]) -> set[str]:
    value = item.get("@type")
    if isinstance(value, str):
        return {value.casefold()}
    if isinstance(value, list):
        return {str(item_type).casefold() for item_type in value if item_type}
    return set()


def _structured_data(items: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    organizations: list[dict[str, Any]] = []
    for item in items:
        types = _schema_types(item)
        if types & {"organization", "corporation"}:
            organization = {
                key: _normalize_json_value(item.get(key))
                for key in ORGANIZATION_FIELDS
                if item.get(key) not in (None, "", [], {})
            }
            if organization:
                organizations.append(organization)
    if organizations:
        result["organizations"] = organizations
        result["organization"] = organizations[0]
    return result


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        if value.get("url"):
            return str(value["url"])
        if value.get("@id"):
            return str(value["@id"])
        address_parts = [
            value.get("streetAddress"),
            value.get("addressLocality"),
            value.get("addressRegion"),
            value.get("postalCode"),
            value.get("addressCountry"),
        ]
        cleaned = [_clean(str(part)) for part in address_parts if part]
        return ", ".join(cleaned) if cleaned else {
            str(key): _normalize_json_value(child)
            for key, child in value.items()
            if not str(key).startswith("@")
        }
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    return _clean(str(value)) if value is not None else ""


def _json_ld_value(items: list[dict[str, Any]], dotted_key: str) -> str:
    keys = dotted_key.split(".")
    for item in items:
        value: Any = item
        for key in keys:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        normalized = _normalize_json_value(value)
        if isinstance(normalized, list):
            normalized = ", ".join(str(part) for part in normalized if part)
        if normalized:
            return str(normalized)
    return ""


def _author_value(items: list[dict[str, Any]]) -> str:
    for item in items:
        value = item.get("author")
        if isinstance(value, dict):
            value = value.get("name")
        elif isinstance(value, list):
            names = [
                child.get("name") if isinstance(child, dict) else child
                for child in value
            ]
            value = ", ".join(str(name) for name in names if name)
        if value:
            return str(value)
    return ""


def _first_text(soup: BeautifulSoup, selector: str) -> str:
    tag = soup.select_one(selector)
    return tag.get_text(" ", strip=True) if tag else ""


def _canonical_url(soup: BeautifulSoup, final_url: str) -> str:
    tag = soup.find("link", attrs={"rel": lambda value: value and "canonical" in value})
    candidate = str(tag.get("href") or "") if isinstance(tag, Tag) else ""
    resolved = urljoin(final_url, candidate) if candidate else final_url
    parsed = urlsplit(resolved)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        resolved = final_url
    return canonicalize_crawl_url(resolved)


def _headings(soup: BeautifulSoup) -> list[str]:
    headings: list[str] = []
    for tag in soup.select("h1, h2, h3, h4"):
        value = _clean(tag.get_text(" ", strip=True))
        if value and value not in headings:
            headings.append(value)
    return headings[:100]


def _links(soup: BeautifulSoup, base_url: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for tag in soup.find_all("a", href=True):
        resolved = urljoin(base_url, str(tag.get("href") or "").strip())
        parsed = urlsplit(resolved)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue
        normalized = canonicalize_crawl_url(resolved)
        if normalized in seen:
            continue
        seen.add(normalized)
        links.append({"url": normalized, "text": _truncate(tag.get_text(" ", strip=True), 160)})
        if len(links) >= MAX_LINKS:
            break
    return links


def _main_text(soup: BeautifulSoup, *, max_content_chars: int) -> str:
    for unwanted in soup(
        ["script", "style", "noscript", "svg", "iframe", "nav", "footer", "header", "aside", "form", "dialog"]
    ):
        unwanted.decompose()
    for tag in soup.find_all(True):
        marker = " ".join(
            [
                str(tag.get("id") or ""),
                " ".join(str(item) for item in tag.get("class") or []),
                str(tag.get("role") or ""),
            ]
        ).casefold()
        if any(
            token in marker
            for token in ("cookie", "consent", "navigation", "navbar", "menu", "breadcrumb", "sidebar", "advert", "promo")
        ):
            tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    blocks: list[str] = []
    seen: set[str] = set()
    for tag in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote", "pre"]):
        value = _clean(tag.get_text(" ", strip=True))
        if len(value) < 2:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        blocks.append(value)
    if not blocks:
        fallback = _clean(root.get_text(" ", strip=True))
        blocks = [fallback] if fallback else []
    text = "\n\n".join(blocks)
    limit = max(2_000, min(500_000, int(max_content_chars)))
    return text[:limit].rstrip()


def _first_content(*values: str) -> str:
    for value in values:
        if _clean(value):
            return value
    return ""


def _clean(value: str) -> str:
    return re.sub(r"[ \t\f\v]+", " ", unescape(value or "")).strip()


def _truncate(value: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", _clean(value)).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 1)].rstrip() + "…"


def _pdf_title(url: str) -> str:
    filename = urlsplit(url).path.rsplit("/", 1)[-1]
    stem = re.sub(r"\.pdf$", "", filename, flags=re.I)
    return _clean(stem.replace("-", " ").replace("_", " ")) or "PDF 报告"
