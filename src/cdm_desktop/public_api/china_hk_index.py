from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from cdm_desktop.public_api.query import normalize_query

CHINA_HK_INDEX_SCHEMA_VERSION = 2
CHINA_HK_INDEX_PATH = (
    Path(__file__).resolve().parents[1]
    / "resources"
    / "china_hk_symbols"
    / "china_hk_symbols.sqlite"
)


def normalize_china_hk_symbol(value: str, market_hint: str = "") -> str:
    text = re.sub(r"[.\s_-]", "", str(value or "").upper())
    if text.startswith(("SH", "SZ", "BJ")) and text[2:].isdigit():
        return f"{text[:2]}{text[2:].zfill(6)}"
    if text.startswith("HK") and text[2:].isdigit():
        return f"HK{text[2:].zfill(5)}"
    if not text.isdigit():
        return text
    hint = market_hint.upper()
    if hint in {"HK", "HKG", "HONG KONG"} or len(text) <= 5:
        return f"HK{text.zfill(5)}"
    code = text.zfill(6)
    if hint in {"BJ", "BSE", "BEIJING"} or code.startswith(("4", "8", "9")):
        return f"BJ{code}"
    if hint in {"SH", "SSE", "SHH", "SHANGHAI"} or code.startswith(("5", "6", "9")):
        return f"SH{code}"
    if hint in {"SZ", "SZSE", "SHZ", "SHENZHEN"} or code.startswith(("0", "2", "3")):
        return f"SZ{code}"
    return code


def index_metadata(path: Path = CHINA_HK_INDEX_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        return {str(key): str(value) for key, value in connection.execute("SELECT key, value FROM metadata")}
    finally:
        connection.close()


def normalized_local_name(value: Any) -> str:
    return normalize_query(str(value or ""))
