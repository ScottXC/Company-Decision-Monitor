from __future__ import annotations

import re


def clean_text(text: str, *, max_chars: int | None = None) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = text.strip()
    if max_chars and len(text) > max_chars:
        return text[:max_chars].rstrip()
    return text
