from __future__ import annotations

from cdm_desktop.config import load_config
from cdm_desktop.connectors.base import (
    BaseConnector,
    NormalizedDocument,
    canonicalize_url,
)
from cdm_desktop.security.url_safety import safe_fetch_url


class ManualUrlConnector(BaseConnector):
    source_type = "manual_url"

    def fetch_documents(self, url: str, config: dict[str, object] | None = None) -> list[NormalizedDocument]:
        settings = load_config()
        config = config or {}
        fetched = safe_fetch_url(
            url,
            timeout_seconds=int(config.get("timeout_seconds", settings.http_timeout_seconds)),
            max_bytes=int(config.get("max_fetch_bytes", settings.max_fetch_bytes)),
        )
        return [
            NormalizedDocument(
                title=None,
                url=fetched.url,
                canonical_url=canonicalize_url(fetched.final_url),
                content_type=fetched.content_type,
                raw_content=fetched.content,
                published_at=None,
                metadata={"status_code": fetched.status_code, "source_type": self.source_type},
            )
        ]
