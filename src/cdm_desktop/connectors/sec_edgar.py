from __future__ import annotations

from pathlib import Path

from cdm_desktop.config import load_config
from cdm_desktop.connectors.base import BaseConnector, NormalizedDocument, canonicalize_url
from cdm_desktop.security.url_safety import safe_fetch_url


class SecEdgarConnector(BaseConnector):
    source_type = "sec_edgar"

    def fetch_documents(self, url: str, config: dict[str, object] | None = None) -> list[NormalizedDocument]:
        config = config or {}
        fixture_text = config.get("fixture_text")
        fixture_path = config.get("fixture_path")
        if isinstance(fixture_text, str) and fixture_text.strip():
            return [
                NormalizedDocument(
                    title="SEC EDGAR fixture filing",
                    url=url,
                    canonical_url=canonicalize_url(url),
                    content_type="text/plain; charset=utf-8",
                    raw_content=fixture_text.encode("utf-8"),
                    metadata={"source_type": self.source_type, "fixture": True},
                )
            ]
        if isinstance(fixture_path, str) and fixture_path.strip():
            path = Path(fixture_path)
            raw = path.read_bytes()
            return [
                NormalizedDocument(
                    title=path.name,
                    url=url,
                    canonical_url=canonicalize_url(url),
                    content_type="text/plain; charset=utf-8",
                    raw_content=raw,
                    metadata={"source_type": self.source_type, "fixture_path": str(path)},
                )
            ]

        settings = load_config()
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
                metadata={"source_type": self.source_type, "status_code": fetched.status_code},
            )
        ]
