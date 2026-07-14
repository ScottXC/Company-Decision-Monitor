from __future__ import annotations

import sqlite3
from pathlib import Path

import akshare

from cdm_desktop.paths import AppPaths
from cdm_desktop.public_api.china_hk_index import CHINA_HK_INDEX_PATH, normalize_china_hk_symbol
from cdm_desktop.public_api.http_client import PublicHttpClient
from cdm_desktop.public_api.key_store import ApiKeyStore
from cdm_desktop.public_api.providers import ChinaHkSymbolProvider
from cdm_desktop.public_api.registry import ProviderRegistry


def paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=tmp_path,
        logs_dir=tmp_path / "logs",
        raw_documents_dir=tmp_path / "raw",
        exports_dir=tmp_path / "exports",
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "cdm.db",
    )


def provider(tmp_path: Path) -> ChinaHkSymbolProvider:
    meta = next(item for item in ProviderRegistry().all() if item.provider_id == "china_hk_symbol_index")
    return ChinaHkSymbolProvider(meta, ApiKeyStore(paths(tmp_path)), PublicHttpClient())


def test_akshare_is_bundled_and_pinned() -> None:
    assert akshare.__version__ == "1.18.64"
    assert "akshare==1.18.64" in Path("requirements-desktop.txt").read_text(encoding="utf-8")


def test_china_hk_symbol_normalization() -> None:
    assert normalize_china_hk_symbol("600519") == "SH600519"
    assert normalize_china_hk_symbol("002594") == "SZ002594"
    assert normalize_china_hk_symbol("300750") == "SZ300750"
    assert normalize_china_hk_symbol("430047") == "BJ430047"
    assert normalize_china_hk_symbol("700") == "HK00700"
    assert normalize_china_hk_symbol("09988") == "HK09988"
    assert normalize_china_hk_symbol("HK00005") == "HK00005"


def test_china_hk_index_schema_and_metadata() -> None:
    assert CHINA_HK_INDEX_PATH.exists()
    connection = sqlite3.connect(CHINA_HK_INDEX_PATH)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"symbols", "aliases", "metadata", "symbols_fts", "name_ngrams"} <= tables
        metadata = dict(connection.execute("SELECT key,value FROM metadata"))
        assert metadata["schema_version"] == "2"
        assert int(metadata["a_share_record_count"]) > 1000
        assert int(metadata["hk_share_record_count"]) > 100
        assert int(metadata["alias_count"]) > 1000
    finally:
        connection.close()


def test_china_hk_provider_exact_and_chinese_alias_search(tmp_path: Path) -> None:
    item = provider(tmp_path)
    cases = {
        "600519": "SH600519",
        "贵州茅台": "SH600519",
        "002594": "SZ002594",
        "比亚迪": "SZ002594",
        "00700": "HK00700",
        "腾讯": "HK00700",
        "09988": "HK09988",
        "阿里巴巴": "HK09988",
    }
    for query, expected in cases.items():
        rows, _news, error = item.search(query, limit=5)
        assert error is None
        assert expected in {row.symbol for row in rows}


def test_china_hk_profile_contains_only_source_fields(tmp_path: Path) -> None:
    item = provider(tmp_path)
    rows, _news, error = item.search("600519", limit=1)
    assert error is None
    profile, profile_error = item.profile(rows[0])
    assert profile_error is None
    assert profile is not None
    assert profile.symbol == "SH600519"
    assert profile.price in {None, ""}
    assert profile.market_cap in {None, ""}
    assert profile.provider_sources == ["china_hk_symbol_index"]
    assert profile.raw["from_local_index"] is True


def test_packaging_declares_akshare_and_index() -> None:
    build = Path("scripts/build_windows.py").read_text(encoding="utf-8")
    validator = Path("scripts/validate_release_artifacts.py").read_text(encoding="utf-8")
    notices = Path("THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert '--collect-submodules", "akshare' in build
    assert "CHINA_HK_INDEX" in build
    assert "--self-test\", \"akshare" in build
    assert "CHINA_HK_INDEX_SUFFIX" in validator
    assert Path("third_party/licenses/AKShare_LICENSE.txt").exists()
    assert "AKShare 1.18.64" in notices
    assert "xq_a_token" not in notices
