from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from cdm_desktop.db.models import OnlineProviderCache, OnlineSearchResult, RecentSearch, utc_now
from cdm_desktop.db.repositories import dumps_json, loads_json
from cdm_desktop.search.models import CompanySearchCandidate, ProviderSearchResponse, SearchScope


class OnlineSearchCache:
    def __init__(self, session: Session, ttl_hours: int = 24) -> None:
        self.session = session
        self.ttl_hours = ttl_hours

    def get_search(self, query: str, scope: SearchScope) -> tuple[list[CompanySearchCandidate], list[dict[str, object]]] | None:
        now = datetime.now(UTC).replace(tzinfo=None)
        item = self.session.scalar(
            select(OnlineSearchResult)
            .where(
                OnlineSearchResult.query == query.strip().lower(),
                OnlineSearchResult.scope == scope,
                OnlineSearchResult.expires_at > now,
            )
            .order_by(OnlineSearchResult.created_at.desc())
            .limit(1)
        )
        if item is None:
            return None
        data = loads_json(item.results_json, []) or []
        statuses = loads_json(item.provider_status_json, []) or []
        return [CompanySearchCandidate.from_dict(row) for row in data], statuses

    def put_search(
        self,
        query: str,
        scope: SearchScope,
        candidates: list[CompanySearchCandidate],
        provider_responses: list[ProviderSearchResponse],
    ) -> None:
        self.session.add(
            OnlineSearchResult(
                query=query.strip().lower(),
                scope=scope,
                results_json=dumps_json([item.to_dict() for item in candidates]),
                provider_status_json=dumps_json(
                    [
                        {
                            "provider_id": response.provider_id,
                            "status": response.status,
                            "error_message": response.error_message,
                            "from_cache": response.from_cache,
                        }
                        for response in provider_responses
                    ]
                ),
                created_at=utc_now(),
                expires_at=utc_now() + timedelta(hours=self.ttl_hours),
            )
        )
        self.session.add(RecentSearch(query=query.strip(), created_at=utc_now()))

    def get_provider_payload(self, provider_id: str, cache_key: str) -> str | None:
        now = datetime.now(UTC).replace(tzinfo=None)
        item = self.session.scalar(
            select(OnlineProviderCache)
            .where(
                OnlineProviderCache.provider_id == provider_id,
                OnlineProviderCache.cache_key == cache_key,
                OnlineProviderCache.expires_at > now,
                OnlineProviderCache.status == "success",
            )
            .order_by(OnlineProviderCache.fetched_at.desc())
            .limit(1)
        )
        return item.payload_path_or_json if item else None

    def put_provider_payload(
        self,
        provider_id: str,
        cache_key: str,
        payload: str,
        *,
        source_url: str,
        status: str = "success",
    ) -> None:
        existing = self.session.scalar(
            select(OnlineProviderCache).where(
                and_(
                    OnlineProviderCache.provider_id == provider_id,
                    OnlineProviderCache.cache_key == cache_key,
                )
            )
        )
        if existing is None:
            existing = OnlineProviderCache(provider_id=provider_id, cache_key=cache_key)
            self.session.add(existing)
        existing.payload_path_or_json = payload
        existing.fetched_at = utc_now()
        existing.expires_at = utc_now() + timedelta(hours=self.ttl_hours)
        existing.source_url = source_url
        existing.status = status
