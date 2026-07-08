from __future__ import annotations

from cdm_desktop.types import WatchlistItem


async def list_watchlist() -> list[WatchlistItem]:
    """Future extension point for persisted watchlist data.

    Compatibility placeholder. Persistent watchlist lives in cdm_desktop.public_api.
    """

    return []
