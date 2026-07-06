from __future__ import annotations

from dataclasses import dataclass

from cdm_desktop.db.repositories import dumps_json
from cdm_desktop.parsing.html_parser import parse_html
from cdm_desktop.parsing.pdf_parser import parse_pdf
from cdm_desktop.parsing.text_cleaner import clean_text


@dataclass(frozen=True)
class ParsedDocument:
    title: str | None
    parsed_text: str
    parse_status: str
    parse_error: str | None
    metadata_json: str


class ParsingService:
    def parse(self, raw_content: bytes, content_type: str | None, fallback_title: str | None = None) -> ParsedDocument:
        content_type = (content_type or "").lower()
        try:
            if "pdf" in content_type:
                result = parse_pdf(raw_content)
                return ParsedDocument(
                    title=result.title or fallback_title,
                    parsed_text=result.text,
                    parse_status="success",
                    parse_error=None,
                    metadata_json=dumps_json(result.metadata),
                )
            if "html" in content_type or raw_content.lstrip().startswith((b"<html", b"<!doctype", b"<")):
                result = parse_html(raw_content)
                return ParsedDocument(
                    title=result.title or fallback_title,
                    parsed_text=result.text,
                    parse_status="success",
                    parse_error=None,
                    metadata_json=dumps_json(result.metadata),
                )

            text = raw_content.decode("utf-8", errors="replace")
            return ParsedDocument(
                title=fallback_title,
                parsed_text=clean_text(text),
                parse_status="success",
                parse_error=None,
                metadata_json=dumps_json({"parser": "plain-text"}),
            )
        except Exception as exc:
            return ParsedDocument(
                title=fallback_title,
                parsed_text="",
                parse_status="failed",
                parse_error=str(exc),
                metadata_json=dumps_json({"parser": "failed"}),
            )
