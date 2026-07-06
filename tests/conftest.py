from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_preview_data_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_dir = Path.cwd() / ".test_runtime" / "cdm-preview"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CDM_DESKTOP_DATA_DIR", str(runtime_dir))
    for key in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
