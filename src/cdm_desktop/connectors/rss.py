from __future__ import annotations

from datetime import datetime

import feedparser
from dateutil.parser import parse as parse_date

from cdm_desktop.config import load_config
from cdm_desktop.connectors.base import BaseConnector, NormalizedDocument, canonicalize_url
from cdm_desktop.security.url_safety import UnsafeUrlError, safe_fetch_url, validate_url


class RSSConnector(BaseConnector):
    source_type = "rss"

    def fetch_documents(self, url: str, config: dict[str, object] | None = None) -> list[NormalizedDocument]:
        settings = load_config()
        config = config or {}
        fetched = safe_fetch_url(
            url,
            timeout_seconds=int(config.get("timeout_seconds", settings.http_timeout_seconds)),
            max_bytes=int(config.get("max_fetch_bytes", settings.max_fetch_bytes)),
        )
        feed = feedparser.parse(fetched.content)
        documents: list[NormalizedDocument] = []
        for entry in feed.entries:
            title = str(getattr(entry, "title", "") or "").strip() or None
            link = str(getattr(entry, "link", "") or "").strip() or fetched.final_url
            published_at = _entry_date(entry)
            summary = str(getattr(entry, "summary", "") or getattr(entry, "description", "") or "")
            raw_content = summary.encode("utf-8", errors="replace")
            content_type = "text/html; charset=utf-8"

            if link and bool(config.get("fetch_articles", True)):
                try:
                    validate_url(link)
                    article = safe_fetch_url(
                        link,
                        timeout_seconds=int(config.get("timeout_seconds", settings.http_timeout_seconds)),
                        max_bytes=int(config.get("max_fetch_bytes", settings.max_fetch_bytes)),
                    )
                    raw_content = article.content
                    content_type = article.content_type
                    link = article.final_url
                except (UnsafeUrlError, Exception):
                    pass

            documents.append(
                NormalizedDocument(
                    title=title,
                    url=link,
                    canonical_url=canonicalize_url(link),
                    content_type=content_type,
                    raw_content=raw_content,
                    published_at=published_at,
                    metadata={"feed_url": fetched.final_url, "source_type": self.source_type},
                )
            )
        return documents


def _entry_date(entry: object) -> datetime | None:
    for attr in ("published", "updated", "created"):
        value = getattr(entry, attr, None)
        if value:
            try:
                return parse_date(str(value)).replace(tzinfo=None)
            except (TypeError, ValueError, OverflowError):
                return None
    return None
