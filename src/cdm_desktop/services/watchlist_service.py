from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from cdm_desktop.db.models import Company
from cdm_desktop.db.repositories import (
    CompanyRepository,
    WatchlistRepository,
    dumps_json,
)
from cdm_desktop.search.models import CompanySearchCandidate
from cdm_desktop.services.recycle_bin_service import RecycleBinService


@dataclass(frozen=True)
class WatchlistResult:
    company_id: int
    added: bool
    message: str


class WatchlistService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_to_watchlist(self, candidate: CompanySearchCandidate) -> WatchlistResult:
        company = self._resolve_company(candidate)
        was_active = WatchlistRepository(self.session).is_active(company.id)
        WatchlistRepository(self.session).add(company.id)
        return WatchlistResult(
            company_id=company.id,
            added=not was_active,
            message="已加入自选" if not was_active else "已在自选中",
        )

    def remove_from_watchlist(self, company_id: int) -> WatchlistResult:
        RecycleBinService(self.session).move_watchlist_company_to_recycle(company_id)
        return WatchlistResult(company_id=company_id, added=False, message="已移入回收站，历史数据已保留")

    def list_watchlist(self, query: str = "", limit: int = 500) -> list[Company]:
        return WatchlistRepository(self.session).list_active(query=query, limit=limit)

    def is_watchlisted(self, company_id: int) -> bool:
        return WatchlistRepository(self.session).is_active(company_id)

    def _resolve_company(self, candidate: CompanySearchCandidate) -> Company:
        if candidate.company_id:
            return CompanyRepository(self.session).get(candidate.company_id)

        existing = self._find_existing(candidate.name, candidate.ticker or None)
        if existing:
            self._merge_aliases(existing.id, candidate.aliases)
            existing.source_provider = existing.source_provider or candidate.source_provider
            existing.source_url = existing.source_url or candidate.source_url
            existing.source_metadata_json = existing.source_metadata_json or candidate.raw_payload_json
            return existing
        company = CompanyRepository(self.session).create(
            name=candidate.name,
            legal_name=candidate.legal_name or None,
            ticker=candidate.ticker or None,
            exchange=candidate.exchange or None,
            country=candidate.country or None,
            industry=candidate.industry or None,
            notes=f"来自公开来源：{candidate.source_provider}" + (f"；{candidate.coverage_note}" if candidate.coverage_note else ""),
            source_provider=candidate.source_provider or None,
            source_url=candidate.source_url or None,
            source_metadata_json=dumps_json(
                {
                    "raw_payload_json": candidate.raw_payload_json,
                    "market": candidate.market,
                    "source_type": candidate.source_type,
                    "coverage_note": candidate.coverage_note,
                    "contributing_providers": candidate.contributing_providers,
                }
            ),
            add_to_watchlist=False,
        )
        self._merge_aliases(company.id, candidate.aliases)
        return company

    def _find_existing(self, name: str, ticker: str | None) -> Company | None:
        conditions = [Company.name == name]
        if ticker:
            conditions.append(Company.ticker == ticker)
        return self.session.scalar(select(Company).where(or_(*conditions)).limit(1))

    def _merge_aliases(self, company_id: int, aliases: tuple[str, ...]) -> None:
        repo = CompanyRepository(self.session)
        for alias in aliases:
            if alias.strip():
                repo.add_alias(company_id, alias.strip(), "other")
