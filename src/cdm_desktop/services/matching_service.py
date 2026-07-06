from __future__ import annotations

from sqlalchemy.orm import Session

from cdm_desktop.db.models import Company
from cdm_desktop.db.repositories import CompanyRepository
from cdm_desktop.event_engine.matcher import (
    CompanyAliasProfile,
    CompanyMatcher,
    CompanyProfile,
    MatchResult,
)


class MatchingService:
    def __init__(self) -> None:
        self.matcher = CompanyMatcher()

    def match_document(self, session: Session, text: str) -> list[MatchResult]:
        companies = CompanyRepository(session).list()
        profiles = [_profile_from_company(company) for company in companies]
        return self.matcher.match_text(text, profiles)


def _profile_from_company(company: Company) -> CompanyProfile:
    aliases = tuple(CompanyAliasProfile(alias=item.alias, alias_type=item.alias_type) for item in company.aliases)
    return CompanyProfile(id=company.id, name=company.name, ticker=company.ticker, aliases=aliases)
