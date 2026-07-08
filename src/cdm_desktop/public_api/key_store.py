from __future__ import annotations

import json

from cdm_desktop.paths import AppPaths, get_app_paths


def mask_secret(value: str | None) -> str:
    if not value:
        return "未配置"
    cleaned = value.strip()
    if len(cleaned) <= 8:
        return "*" * len(cleaned)
    return f"{cleaned[:4]}...{cleaned[-4:]}"


class ApiKeyStore:
    def __init__(self, paths: AppPaths | None = None) -> None:
        self.paths = paths or get_app_paths()
        self.path = self.paths.app_data_dir / "api_keys.json"

    def get(self, key_name: str) -> str:
        return str(self._read().get(key_name, "") or "")

    def set(self, key_name: str, value: str) -> None:
        data = self._read()
        if value.strip():
            data[key_name] = value.strip()
        else:
            data.pop(key_name, None)
        self._write(data)

    def clear(self, key_name: str) -> None:
        data = self._read()
        data.pop(key_name, None)
        self._write(data)

    def status(self, key_name: str | None) -> tuple[bool, str]:
        if not key_name:
            return True, "无需 key"
        value = self.get(key_name)
        return bool(value), mask_secret(value)

    def all_masked(self) -> dict[str, str]:
        return {key: mask_secret(value) for key, value in self._read().items()}

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {str(k): str(v) for k, v in raw.items() if isinstance(k, str)}

    def _write(self, data: dict[str, str]) -> None:
        self.paths.app_data_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
