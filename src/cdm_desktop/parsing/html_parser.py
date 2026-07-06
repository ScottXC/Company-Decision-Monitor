from __future__ import annotations

from dataclasses import dataclass

from bs4 import BeautifulSoup

from cdm_desktop.parsing.text_cleaner import clean_text


@dataclass(frozen=True)
class HtmlParseResult:
    title: str | None
    text: str
    metadata: dict[str, str]


def parse_html(content: bytes | str) -> HtmlParseResult:
    html = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    text = clean_text(soup.get_text("\n", strip=True))
    return HtmlParseResult(title=title, text=text, metadata={"parser": "beautifulsoup-lxml"})
