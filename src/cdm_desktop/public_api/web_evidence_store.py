from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cdm_desktop.paths import AppPaths, get_app_paths
from cdm_desktop.public_api.web_evidence_models import (
    CrawlJob,
    ProfileFieldCandidate,
    WebEvidenceItem,
)

SCHEMA_VERSION = "1"


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc_value, traceback))
        finally:
            self.close()


class WebEvidenceStore:
    """Independent AppData database for user-triggered public web evidence."""

    def __init__(
        self,
        paths: AppPaths | None = None,
        *,
        db_path: str | Path | None = None,
    ) -> None:
        self.paths = paths or get_app_paths()
        self.db_path = Path(db_path) if db_path is not None else self.paths.web_evidence_db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()
        self.recovered_corrupt_path: Path | None = None
        self.initialize()

    def initialize(self) -> None:
        with self._write_lock:
            try:
                if self.db_path.exists():
                    with self._connect() as connection:
                        result = connection.execute("PRAGMA quick_check").fetchone()
                        if not result or str(result[0]).casefold() != "ok":
                            raise sqlite3.DatabaseError("web_evidence.sqlite quick_check failed")
                self._create_schema()
            except sqlite3.DatabaseError:
                self._preserve_corrupt_database()
                self._create_schema()

    def save_job(self, job: CrawlJob) -> None:
        values = job.to_dict()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO crawl_jobs (
                    id, company_id, company_name, seed_url, seed_urls_json,
                    allowed_domains_json, max_pages, max_depth, timeout_seconds,
                    request_delay_seconds, status, progress, pages_discovered,
                    pages_processed, pages_skipped, started_at, finished_at,
                    cancelled, error_type, error_message, errors_json
                ) VALUES (
                    :id, :company_id, :company_name, :seed_url, :seed_urls_json,
                    :allowed_domains_json, :max_pages, :max_depth, :timeout_seconds,
                    :request_delay_seconds, :status, :progress, :pages_discovered,
                    :pages_processed, :pages_skipped, :started_at, :finished_at,
                    :cancelled, :error_type, :error_message, :errors_json
                )
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    progress=excluded.progress,
                    pages_discovered=excluded.pages_discovered,
                    pages_processed=excluded.pages_processed,
                    pages_skipped=excluded.pages_skipped,
                    finished_at=excluded.finished_at,
                    cancelled=excluded.cancelled,
                    error_type=excluded.error_type,
                    error_message=excluded.error_message,
                    errors_json=excluded.errors_json
                """,
                {
                    **values,
                    "seed_urls_json": _json(values.get("seed_urls", [])),
                    "allowed_domains_json": _json(values.get("allowed_domains", [])),
                    "errors_json": _json(values.get("errors", [])),
                    "cancelled": int(bool(values.get("cancelled"))),
                },
            )

    def save_evidence(self, item: WebEvidenceItem, *, ttl_seconds: int = 86400) -> WebEvidenceItem:
        expires_at = (datetime.now(UTC) + timedelta(seconds=max(3600, ttl_seconds))).isoformat()
        with self._write_lock, self._connect() as connection:
            matches = connection.execute(
                """
                SELECT id FROM web_evidence
                WHERE company_id = ? AND (canonical_url = ? OR content_hash = ?)
                ORDER BY CASE WHEN canonical_url = ? THEN 0 ELSE 1 END
                """,
                (item.company_id, item.canonical_url, item.content_hash, item.canonical_url),
            ).fetchall()
            if matches:
                item.id = str(matches[0]["id"])
                for duplicate in matches[1:]:
                    connection.execute(
                        "DELETE FROM web_evidence WHERE id = ?",
                        (str(duplicate["id"]),),
                    )
            payload = item.to_dict()
            payload.pop("raw_html", None)
            connection.execute(
                """
                INSERT INTO web_evidence (
                    id, company_id, company_name, source_url, final_url, canonical_url,
                    domain, title, description, cleaned_text, content_snippet,
                    content_type, language, author, published_at, modified_at,
                    discovered_at, crawled_at, robots_allowed, is_official_domain,
                    display_mode, provider, content_hash, from_cache, status,
                    error_message, payload_json, expires_at
                ) VALUES (
                    :id, :company_id, :company_name, :source_url, :final_url, :canonical_url,
                    :domain, :title, :description, :cleaned_text, :content_snippet,
                    :content_type, :language, :author, :published_at, :modified_at,
                    :discovered_at, :crawled_at, :robots_allowed, :is_official_domain,
                    :display_mode, :provider, :content_hash, :from_cache, :status,
                    :error_message, :payload_json, :expires_at
                )
                ON CONFLICT(id) DO UPDATE SET
                    company_name=excluded.company_name,
                    source_url=excluded.source_url,
                    final_url=excluded.final_url,
                    canonical_url=excluded.canonical_url,
                    domain=excluded.domain,
                    title=excluded.title,
                    description=excluded.description,
                    cleaned_text=excluded.cleaned_text,
                    content_snippet=excluded.content_snippet,
                    content_type=excluded.content_type,
                    language=excluded.language,
                    author=excluded.author,
                    published_at=excluded.published_at,
                    modified_at=excluded.modified_at,
                    crawled_at=excluded.crawled_at,
                    robots_allowed=excluded.robots_allowed,
                    is_official_domain=excluded.is_official_domain,
                    display_mode=excluded.display_mode,
                    provider=excluded.provider,
                    content_hash=excluded.content_hash,
                    from_cache=excluded.from_cache,
                    status=excluded.status,
                    error_message=excluded.error_message,
                    payload_json=excluded.payload_json,
                    expires_at=excluded.expires_at
                """,
                {
                    **payload,
                    "robots_allowed": int(item.robots_allowed),
                    "is_official_domain": int(item.is_official_domain),
                    "from_cache": int(item.from_cache),
                    "payload_json": _json(payload),
                    "expires_at": expires_at,
                },
            )
            connection.execute("DELETE FROM evidence_links WHERE evidence_id = ?", (item.id,))
            connection.executemany(
                "INSERT OR IGNORE INTO evidence_links (evidence_id, url, link_text) VALUES (?, ?, ?)",
                [
                    (item.id, str(link.get("url") or ""), str(link.get("text") or ""))
                    for link in item.links
                    if link.get("url")
                ],
            )
        return item

    def cached_evidence(
        self,
        company_id: str,
        canonical_url: str,
    ) -> WebEvidenceItem | None:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM web_evidence
                WHERE company_id = ? AND canonical_url = ? AND expires_at > ?
                LIMIT 1
                """,
                (company_id, canonical_url, now),
            ).fetchone()
        if not row:
            return None
        item = _item_from_payload(row["payload_json"])
        if item:
            item.from_cache = True
        return item

    def list_evidence(self, company_id: str) -> list[WebEvidenceItem]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM web_evidence
                WHERE company_id = ?
                ORDER BY crawled_at DESC, title COLLATE NOCASE
                """,
                (company_id,),
            ).fetchall()
        return [item for row in rows if (item := _item_from_payload(row["payload_json"]))]

    def delete_evidence(self, evidence_id: str) -> bool:
        with self._write_lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM web_evidence WHERE id = ?", (evidence_id,))
            return cursor.rowcount > 0

    def clear_company(self, company_id: str) -> int:
        with self._write_lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM web_evidence WHERE company_id = ?", (company_id,))
            connection.execute("DELETE FROM profile_field_candidates WHERE company_id = ?", (company_id,))
            return max(0, cursor.rowcount)

    def clear_all(self) -> int:
        with self._write_lock, self._connect() as connection:
            count = int(connection.execute("SELECT COUNT(*) FROM web_evidence").fetchone()[0])
            connection.execute("DELETE FROM web_evidence")
            connection.execute("DELETE FROM crawl_jobs")
            connection.execute("DELETE FROM crawl_errors")
            connection.execute("DELETE FROM profile_field_candidates")
            return count

    def save_candidate(self, company_id: str, candidate: ProfileFieldCandidate) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO profile_field_candidates (
                    id, company_id, field_name, proposed_value_json, source_url,
                    evidence_id, confidence, current_value_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=CASE
                        WHEN profile_field_candidates.status IN ('accepted', 'rejected')
                            THEN profile_field_candidates.status
                        ELSE excluded.status
                    END
                """,
                (
                    candidate.id,
                    company_id,
                    candidate.field_name,
                    candidate.proposed_value_json(),
                    candidate.source_url,
                    candidate.evidence_id,
                    candidate.confidence,
                    _json(candidate.current_value),
                    candidate.status,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def list_candidates(self, company_id: str) -> list[ProfileFieldCandidate]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM profile_field_candidates
                WHERE company_id = ? ORDER BY created_at DESC
                """,
                (company_id,),
            ).fetchall()
        result: list[ProfileFieldCandidate] = []
        for row in rows:
            result.append(
                ProfileFieldCandidate(
                    id=str(row["id"]),
                    field_name=str(row["field_name"]),
                    proposed_value=_parse_json(row["proposed_value_json"]),
                    source_url=str(row["source_url"]),
                    evidence_id=str(row["evidence_id"]),
                    confidence=float(row["confidence"]),
                    current_value=_parse_json(row["current_value_json"]),
                    status=str(row["status"]),
                )
            )
        return result

    def update_candidate_status(self, candidate_id: str, status: str) -> bool:
        if status not in {"pending", "accepted", "rejected", "auto_accepted"}:
            raise ValueError("未知候选字段状态。")
        with self._write_lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE profile_field_candidates SET status = ? WHERE id = ?",
                (status, candidate_id),
            )
            return cursor.rowcount > 0

    def record_error(
        self,
        job_id: str,
        url: str,
        error_type: str,
        message: str,
    ) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO crawl_errors (job_id, url, error_type, message, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, url, error_type, message, datetime.now(UTC).isoformat()),
            )

    def size_bytes(self) -> int:
        return self.db_path.stat().st_size if self.db_path.exists() else 0

    def integrity_check(self) -> bool:
        try:
            with self._connect() as connection:
                result = connection.execute("PRAGMA integrity_check").fetchone()
            return bool(result and str(result[0]).casefold() == "ok")
        except sqlite3.DatabaseError:
            return False

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.db_path,
            timeout=10,
            check_same_thread=False,
            factory=_ClosingConnection,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _create_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS crawl_jobs (
                    id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    seed_url TEXT NOT NULL,
                    seed_urls_json TEXT NOT NULL,
                    allowed_domains_json TEXT NOT NULL,
                    max_pages INTEGER NOT NULL,
                    max_depth INTEGER NOT NULL,
                    timeout_seconds INTEGER NOT NULL,
                    request_delay_seconds REAL NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL,
                    pages_discovered INTEGER NOT NULL,
                    pages_processed INTEGER NOT NULL,
                    pages_skipped INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    cancelled INTEGER NOT NULL,
                    error_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    errors_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS web_evidence (
                    id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    final_url TEXT NOT NULL,
                    canonical_url TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    cleaned_text TEXT NOT NULL,
                    content_snippet TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    language TEXT NOT NULL,
                    author TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    modified_at TEXT NOT NULL,
                    discovered_at TEXT NOT NULL,
                    crawled_at TEXT NOT NULL,
                    robots_allowed INTEGER NOT NULL,
                    is_official_domain INTEGER NOT NULL,
                    display_mode TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    from_cache INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    UNIQUE(company_id, canonical_url),
                    UNIQUE(company_id, content_hash)
                );
                CREATE INDEX IF NOT EXISTS ix_web_evidence_company_crawled
                    ON web_evidence(company_id, crawled_at DESC);
                CREATE TABLE IF NOT EXISTS evidence_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    evidence_id TEXT NOT NULL REFERENCES web_evidence(id) ON DELETE CASCADE,
                    url TEXT NOT NULL,
                    link_text TEXT NOT NULL,
                    UNIQUE(evidence_id, url)
                );
                CREATE TABLE IF NOT EXISTS crawl_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS crawl_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS profile_field_candidates (
                    id TEXT PRIMARY KEY,
                    company_id TEXT NOT NULL,
                    field_name TEXT NOT NULL,
                    proposed_value_json TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    evidence_id TEXT NOT NULL REFERENCES web_evidence(id) ON DELETE CASCADE,
                    confidence REAL NOT NULL,
                    current_value_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_profile_candidates_company
                    ON profile_field_candidates(company_id, status);
                """
            )
            connection.execute(
                """
                INSERT INTO crawl_metadata(key, value) VALUES('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (SCHEMA_VERSION,),
            )

    def _preserve_corrupt_database(self) -> None:
        if not self.db_path.exists():
            return
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        destination = self.db_path.with_name(f"{self.db_path.name}.corrupted.{timestamp}")
        counter = 1
        while destination.exists():
            destination = self.db_path.with_name(
                f"{self.db_path.name}.corrupted.{timestamp}.{counter}"
            )
            counter += 1
        self.db_path.replace(destination)
        self.recovered_corrupt_path = destination
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{self.db_path}{suffix}")
            if sidecar.exists():
                sidecar.replace(Path(f"{destination}{suffix}"))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _parse_json(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return ""


def _item_from_payload(value: str) -> WebEvidenceItem | None:
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    return WebEvidenceItem.from_dict(payload) if isinstance(payload, dict) else None
