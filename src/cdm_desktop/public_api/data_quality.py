from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cdm_desktop.public_api.models import CompanyProfile


EMPTY_TEXT_VALUES = {
    "",
    "none",
    "null",
    "nan",
    "n/a",
    "-",
    "--",
    "unknown",
    "暂无数据",
}

ZERO_IS_MISSING_FIELDS = {
    "price",
    "previous_close",
    "market_cap",
    "employees",
}


def is_meaningful_value(value: Any, field_name: str = "") -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    if isinstance(value, (int, float)):
        return not (value == 0 and field_name in ZERO_IS_MISSING_FIELDS)
    cleaned = str(value).strip()
    if cleaned.casefold() in EMPTY_TEXT_VALUES:
        return False
    if field_name in ZERO_IS_MISSING_FIELDS:
        try:
            return float(cleaned.replace(",", "")) != 0
        except ValueError:
            pass
    return True


def normalize_profile_value(value: Any, field_name: str = "") -> Any:
    if not is_meaningful_value(value, field_name):
        return ""
    if isinstance(value, str):
        return " ".join(value.strip().split())
    return value


LISTED_PROFILE_FIELDS = (
    "display_name",
    "legal_name",
    "aliases",
    "description",
    "website",
    "company_type",
    "symbol",
    "exchange",
    "market",
    "country",
    "currency",
    "instrument_type",
    "listing_date",
    "sector",
    "industry",
    "lei",
    "jurisdiction",
    "registration_status",
    "legal_address",
    "wikidata_id",
    "wikipedia_url",
)

LEGAL_ENTITY_PROFILE_FIELDS = (
    "display_name",
    "legal_name",
    "aliases",
    "description",
    "website",
    "company_type",
    "entity_type",
    "country",
    "lei",
    "registration_number",
    "company_number",
    "registry_number",
    "jurisdiction",
    "registration_status",
    "entity_status",
    "legal_address",
    "registered_address",
    "address",
)

ENCYCLOPEDIA_PROFILE_FIELDS = (
    "display_name",
    "aliases",
    "description",
    "website",
    "company_type",
    "country",
    "sector",
    "industry",
    "wikidata_id",
    "wikipedia_url",
)

IDENTITY_FIELDS = ("display_name", "symbol", "exchange", "market", "country", "currency", "instrument_type")
MARKET_FIELDS = ("symbol", "exchange", "market", "currency", "price", "market_cap", "listing_date")
CLASSIFICATION_FIELDS = ("company_type", "entity_type", "sector", "industry", "business_scope")
LEGAL_FIELDS = (
    "legal_name",
    "lei",
    "registration_number",
    "company_number",
    "registry_number",
    "jurisdiction",
    "registration_status",
    "entity_status",
    "legal_address",
    "registered_address",
)
CONTACT_FIELDS = ("website", "phone", "email", "address", "city", "state", "postal_code")


@dataclass
class ProfileCoverage:
    populated_fields: int
    total_supported_fields: int
    coverage_percent: int
    identity_coverage: int
    market_coverage: int
    classification_coverage: int
    legal_coverage: int
    contact_coverage: int
    source_count: int
    unresolved_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "populated_fields": self.populated_fields,
            "total_supported_fields": self.total_supported_fields,
            "coverage_percent": self.coverage_percent,
            "identity_coverage": self.identity_coverage,
            "market_coverage": self.market_coverage,
            "classification_coverage": self.classification_coverage,
            "legal_coverage": self.legal_coverage,
            "contact_coverage": self.contact_coverage,
            "source_count": self.source_count,
            "unresolved_fields": self.unresolved_fields,
        }


def _percent(profile: CompanyProfile, fields: tuple[str, ...]) -> int:
    if not fields:
        return 0
    found = sum(is_meaningful_value(getattr(profile, name, None), name) for name in fields)
    return round(found * 100 / len(fields))


def profile_supported_fields(profile: CompanyProfile) -> tuple[str, ...]:
    if profile.company_type == "legal_entity" or (profile.lei and not profile.symbol):
        return LEGAL_ENTITY_PROFILE_FIELDS
    if profile.company_type == "encyclopedia_entity" or (profile.wikidata_id and not profile.symbol):
        return ENCYCLOPEDIA_PROFILE_FIELDS
    return LISTED_PROFILE_FIELDS


def missing_profile_fields(profile: CompanyProfile) -> list[str]:
    fields = profile_supported_fields(profile)
    return [name for name in fields if not is_meaningful_value(getattr(profile, name, None), name)]


def profile_coverage(profile: CompanyProfile) -> ProfileCoverage:
    supported_fields = profile_supported_fields(profile)
    missing = missing_profile_fields(profile)
    populated = len(supported_fields) - len(missing)
    if profile.company_type == "legal_entity" or (profile.lei and not profile.symbol):
        identity_fields = ("display_name", "legal_name", "lei", "jurisdiction", "country")
        market_fields: tuple[str, ...] = ()
    elif profile.company_type == "encyclopedia_entity" or (profile.wikidata_id and not profile.symbol):
        identity_fields = ("display_name", "description", "wikidata_id", "wikipedia_url")
        market_fields = ()
    else:
        identity_fields = IDENTITY_FIELDS
        market_fields = MARKET_FIELDS
    return ProfileCoverage(
        populated_fields=populated,
        total_supported_fields=len(supported_fields),
        coverage_percent=round(populated * 100 / len(supported_fields)),
        identity_coverage=_percent(profile, identity_fields),
        market_coverage=_percent(profile, market_fields),
        classification_coverage=_percent(profile, CLASSIFICATION_FIELDS),
        legal_coverage=_percent(profile, LEGAL_FIELDS),
        contact_coverage=_percent(profile, CONTACT_FIELDS),
        source_count=len(set(profile.provider_sources)),
        unresolved_fields=missing,
    )
