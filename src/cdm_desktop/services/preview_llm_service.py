from __future__ import annotations


async def summarize_company(company_id: str) -> str | None:
    """Future extension point for optional LLM summaries.

    Compatibility placeholder. Public + Free API Network Mode does not enable LLM summary yet.
    """

    _ = company_id
    return None
