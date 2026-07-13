from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_third_party_notices_and_license_files_exist() -> None:
    assert (ROOT / "THIRD_PARTY_NOTICES.md").exists()
    for name in [
        "RapidFuzz_LICENSE.txt",
        "cleanco_LICENSE.txt",
        "FinanceDatabase_LICENSE.txt",
    ]:
        assert (ROOT / "third_party" / "licenses" / name).exists()


def test_symbol_universe_index_is_bundled_resource() -> None:
    index = ROOT / "src" / "cdm_desktop" / "resources" / "symbol_universe" / "symbol_universe.sqlite"

    assert index.exists()
    assert index.stat().st_size > 1024 * 1024


def test_crawlergo_binary_not_bundled_in_project_resources() -> None:
    resource_root = ROOT / "src" / "cdm_desktop" / "resources"
    binaries = [
        path
        for path in resource_root.rglob("*")
        if path.is_file() and path.name.lower() in {"crawlergo.exe", "crawlergo"}
    ]

    assert binaries == []


def test_readme_documents_bundled_runtime_and_no_required_api_key() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "v0.1.3-bundled-open-source-runtime" in readme
    assert "do not need Python" in readme
    assert "do not need to apply for API keys" in readme
    assert "crawlergo" in readme
    assert "not bundled" in readme
