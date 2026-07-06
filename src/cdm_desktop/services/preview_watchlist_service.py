from __future__ import annotations

from cdm_desktop.types import WatchlistItem


async def list_watchlist() -> list[WatchlistItem]:
    """Future extension point for persisted watchlist data.

    UI Preview Mode intentionally starts empty and does not read historical user data.
    """

    return []
