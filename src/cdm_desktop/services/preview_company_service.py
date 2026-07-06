from __future__ import annotations

from cdm_desktop.types import CompanyProfile, FinancialMetric


async def get_company_profile(company_id: str) -> CompanyProfile | None:
    """Future extension point for company profile and financial databases."""

    _ = company_id
    return None


async def get_financial_metrics(company_id: str) -> list[FinancialMetric]:
    """Future extension point for financial statement and market metric data."""

    _ = company_id
    return []
