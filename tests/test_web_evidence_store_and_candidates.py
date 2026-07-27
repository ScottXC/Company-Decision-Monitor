from __future__ import annotations

import sqlite3
from pathlib import Path

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.models import CompanyProfile
from cdm_desktop.public_api.profile_candidates import (
    apply_auto_accepted_candidates,
    profile_candidates_from_evidence,
)
from cdm_desktop.public_api.web_evidence_models import WebEvidenceItem
from cdm_desktop.public_api.web_evidence_store import WebEvidenceStore


def make_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        raw_documents_dir=tmp_path / "raw_documents",
        exports_dir=tmp_path / "exports",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "cdm.db",
    ).ensure()


def evidence(
    *,
    canonical_url: str = "https://example.com/a",
    content_hash: str = "hash-a",
    item_id: str = "evidence-a",
) -> WebEvidenceItem:
    return WebEvidenceItem(
        id=item_id,
        company_id="company:1",
        company_name="Example",
        source_url=canonical_url,
        final_url=canonical_url,
        canonical_url=canonical_url,
        domain="example.com",
        title="Example evidence",
        description="Public information",
        cleaned_text="Official cleaned text",
        content_snippet="Official cleaned text",
        display_mode="full_cleaned_text",
        is_official_domain=True,
        content_hash=content_hash,
        links=[{"url": "https://example.com/b", "text": "B"}],
        structured_data={
            "organization": {
                "name": "Example Corp",
                "legalName": "Example Corporation",
                "alternateName": "Example",
                "url": "https://example.com/",
                "logo": "https://example.com/logo.png",
                "address": "1 Main Street",
                "telephone": "+65 1234",
                "email": "ir@example.com",
                "foundingDate": "2001-01-02",
            }
        },
    )


def test_store_insert_canonical_and_content_hash_dedup_delete_and_clear(tmp_path: Path) -> None:
    store = WebEvidenceStore(make_paths(tmp_path))
    first = store.save_evidence(evidence())
    canonical_duplicate = evidence(content_hash="hash-b", item_id="evidence-b")
    store.save_evidence(canonical_duplicate)
    hash_duplicate = evidence(
        canonical_url="https://example.com/other",
        content_hash="hash-b",
        item_id="evidence-c",
    )
    store.save_evidence(hash_duplicate)

    items = store.list_evidence("company:1")
    assert len(items) == 1
    assert items[0].id == first.id
    assert store.integrity_check()
    assert store.delete_evidence(first.id)
    assert store.list_evidence("company:1") == []

    store.save_evidence(evidence(item_id="replacement"))
    assert store.clear_company("company:1") == 1
    assert store.clear_all() == 0


def test_store_schema_has_required_tables_and_no_raw_html(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    store = WebEvidenceStore(paths)
    store.save_evidence(evidence())

    with sqlite3.connect(paths.web_evidence_db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {
        "crawl_jobs",
        "web_evidence",
        "evidence_links",
        "crawl_errors",
        "crawl_metadata",
        "profile_field_candidates",
    }.issubset(tables)
    raw = paths.web_evidence_db_path.read_bytes().lower()
    assert b"<html" not in raw
    assert b"cookie=" not in raw
    assert b"authorization" not in raw


def test_corrupted_web_evidence_database_is_preserved_and_rebuilt(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    paths.web_evidence_db_path.write_bytes(b"not a sqlite database")

    store = WebEvidenceStore(paths)

    assert store.recovered_corrupt_path is not None
    assert store.recovered_corrupt_path.exists()
    assert store.integrity_check()
    assert store.list_evidence("company:1") == []


def test_official_json_ld_candidates_auto_accept_only_empty_fields() -> None:
    item = evidence()
    profile = CompanyProfile()
    candidates = profile_candidates_from_evidence(item, profile)

    legal = next(candidate for candidate in candidates if candidate.field_name == "legal_name")
    assert legal.status == "auto_accepted"
    apply_auto_accepted_candidates(profile, candidates)
    assert profile.legal_name == "Example Corporation"
    assert profile.website == "https://example.com/"
    assert profile.aliases == ["Example"]
    assert profile.field_sources["legal_name"] == "official_website_evidence"
    assert profile.field_candidates["legal_name"][0]["source_url"] == item.canonical_url


def test_conflicting_or_third_party_candidate_is_not_auto_applied() -> None:
    official = evidence()
    profile = CompanyProfile(legal_name="Existing Legal Name")
    candidates = profile_candidates_from_evidence(official, profile)
    legal = next(candidate for candidate in candidates if candidate.field_name == "legal_name")
    assert legal.status == "pending"
    apply_auto_accepted_candidates(profile, candidates)
    assert profile.legal_name == "Existing Legal Name"

    third_party = evidence(item_id="third-party")
    third_party.is_official_domain = False
    third_party.display_mode = "excerpt_only"
    assert profile_candidates_from_evidence(third_party, CompanyProfile()) == []


def test_candidates_persist_with_traceable_evidence(tmp_path: Path) -> None:
    store = WebEvidenceStore(make_paths(tmp_path))
    item = store.save_evidence(evidence())
    candidates = profile_candidates_from_evidence(item, CompanyProfile())
    for candidate in candidates:
        store.save_candidate(item.company_id, candidate)

    loaded = store.list_candidates(item.company_id)
    assert loaded
    assert all(candidate.source_url == item.canonical_url for candidate in loaded)
    assert all(candidate.evidence_id == item.id for candidate in loaded)
    assert store.update_candidate_status(loaded[0].id, "accepted")
    updated = next(
        candidate
        for candidate in store.list_candidates(item.company_id)
        if candidate.id == loaded[0].id
    )
    assert updated.status == "accepted"
