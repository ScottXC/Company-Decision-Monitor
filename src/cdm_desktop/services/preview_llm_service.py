from __future__ import annotations


async def summarize_company(company_id: str) -> str | None:
    """Future extension point for optional LLM summaries.

    No model, API key, or remote call is used in UI Preview Mode.
    """

    _ = company_id
    return None
