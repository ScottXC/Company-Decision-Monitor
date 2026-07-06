from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PreviewUiState:
    current_route: str = "/dashboard"
    search_keyword: str = ""
    search_scope: str = "all"
    theme: str = "system"
