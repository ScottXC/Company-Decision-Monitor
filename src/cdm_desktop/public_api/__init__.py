"""Public and free-tier API integration layer."""

from cdm_desktop.public_api.models import (
    ApiKeyDefinition,
    CompanyProfile,
    CompanyResult,
    ExternalSourceLink,
    NewsItem,
    ProviderStatus,
    SearchResponse,
)
from cdm_desktop.public_api.news_service import CompanyNewsService
from cdm_desktop.public_api.profile_service import CompanyProfileService
from cdm_desktop.public_api.registry import ProviderRegistry
from cdm_desktop.public_api.search_service import PublicSearchService
from cdm_desktop.public_api.xueqiu_external_link import (
    XueqiuCommunityLinkProvider,
    build_xueqiu_external_link,
    normalize_xueqiu_symbol,
)

__all__ = [
    "ApiKeyDefinition",
    "CompanyNewsService",
    "CompanyProfile",
    "CompanyProfileService",
    "CompanyResult",
    "ExternalSourceLink",
    "NewsItem",
    "ProviderRegistry",
    "ProviderStatus",
    "PublicSearchService",
    "SearchResponse",
    "XueqiuCommunityLinkProvider",
    "build_xueqiu_external_link",
    "normalize_xueqiu_symbol",
]
