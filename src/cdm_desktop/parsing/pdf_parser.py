from __future__ import annotations

from dataclasses import dataclass

import fitz

from cdm_desktop.parsing.text_cleaner import clean_text


@dataclass(frozen=True)
class PdfParseResult:
    title: str | None
    text: str
    metadata: dict[str, object]


def parse_pdf(content: bytes) -> PdfParseResult:
    with fitz.open(stream=content, filetype="pdf") as document:
        page_text = [page.get_text("text") for page in document]
        metadata = dict(document.metadata or {})
        metadata["page_count"] = document.page_count
    title = str(metadata.get("title") or "").strip() or None
    return PdfParseResult(title=title, text=clean_text("\n".join(page_text)), metadata=metadata)
