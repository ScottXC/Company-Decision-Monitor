from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urldefrag, urlparse, urlunparse


@dataclass(frozen=True)
class NormalizedDocument:
    title: str | None
    url: str
    canonical_url: str
    content_type: str
    raw_content: bytes
    published_at: datetime | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class ConnectorError(RuntimeError):
    pass


class BaseConnector:
    source_type = "base"

    def fetch_documents(self, url: str, config: dict[str, object] | None = None) -> list[NormalizedDocument]:
        raise NotImplementedError


def canonicalize_url(url: str) -> str:
    clean_url, _fragment = urldefrag(url.strip())
    parsed = urlparse(clean_url)
    if not parsed.scheme or not parsed.netloc:
        return clean_url
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            "",
            parsed.query,
            "",
        )
    )


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
