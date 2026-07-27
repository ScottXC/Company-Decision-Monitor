from __future__ import annotations

import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cdm_desktop.public_api.crawl_safety import validate_crawl_url
from cdm_desktop.public_api.web_evidence_models import CrawlPolicy

CRAWLERGO_DISTRIBUTION_LICENSE = "GPL-3.0"
CRAWLERGO_DISCOVERY_ENABLED = False
CRAWLERGO_SAFETY_NOTE = (
    "当前上游 crawlergo 无法关闭表单提交与 DOM 事件触发；本版本仅检测可选运行时，"
    "实际网页证据采集使用受控 GET-only 管线。"
)


@dataclass(frozen=True, slots=True)
class CrawlergoRuntimeStatus:
    state: str
    mode: str
    binary_path: str = ""
    chrome_path: str = ""
    binary_status: str = "missing"
    chrome_status: str = "missing"
    configured: bool = False
    bundled: bool = False
    message: str = ""
    license_name: str = CRAWLERGO_DISTRIBUTION_LICENSE
    discovery_enabled: bool = CRAWLERGO_DISCOVERY_ENABLED


@dataclass(frozen=True, slots=True)
class CrawlergoCommand:
    command: list[str]
    allowed_domains: list[str]
    max_depth: int
    timeout_seconds: int
    shell: bool = False


@dataclass(slots=True)
class RuntimeTestResult:
    state: str
    message: str
    binary_version: str = ""
    chrome_version: str = ""


class CrawlergoRuntimeManager:
    def __init__(
        self,
        *,
        external_binary_path: str = "",
        external_chrome_path: str = "",
        app_dir: str | Path | None = None,
    ) -> None:
        self.external_binary_path = external_binary_path.strip()
        self.external_chrome_path = external_chrome_path.strip()
        self.app_dir = Path(app_dir) if app_dir is not None else _application_dir()
        self._processes: set[subprocess.Popen[str]] = set()
        self._lock = threading.Lock()

    def discover(self) -> CrawlergoRuntimeStatus:
        bundled_binary = _first_file(self._bundled_binary_candidates())
        bundled_chrome = _first_file(self._bundled_chrome_candidates())
        if bundled_binary:
            if not self._bundled_license_ready():
                return CrawlergoRuntimeStatus(
                    state="dependency_error",
                    mode="bundled",
                    binary_path=str(bundled_binary),
                    chrome_path=str(bundled_chrome or ""),
                    binary_status="blocked_by_license_audit",
                    chrome_status="available" if bundled_chrome else "missing",
                    configured=True,
                    bundled=True,
                    message="检测到内置 crawlergo，但许可证文件或源码获取说明不完整，已禁用。",
                )
            return self._status_for_paths(
                "bundled",
                bundled_binary,
                bundled_chrome,
                bundled=True,
            )

        system_binary = _which_file(("crawlergo", "crawlergo.exe"))
        system_chrome = _first_file(self._system_chrome_candidates())
        if system_binary:
            return self._status_for_paths("system", system_binary, system_chrome)

        external_binary = _validated_file(self.external_binary_path)
        external_chrome = _validated_file(self.external_chrome_path) or system_chrome
        if external_binary:
            return self._status_for_paths("external", external_binary, external_chrome)

        return CrawlergoRuntimeStatus(
            state="dependency_missing",
            mode="optional_external",
            chrome_path=str(external_chrome or system_chrome or ""),
            binary_status="missing",
            chrome_status="available" if external_chrome or system_chrome else "missing",
            configured=bool(self.external_binary_path),
            message=(
                "crawlergo_optional_external：未发现 crawlergo；网页证据仍可使用安全 GET-only 采集。"
            ),
        )

    def test_runtime(self, *, timeout_seconds: int = 5) -> RuntimeTestResult:
        status = self.discover()
        if status.state == "dependency_missing":
            return RuntimeTestResult(status.state, status.message)
        if status.state != "enabled":
            return RuntimeTestResult(status.state, status.message)

        binary_result = self._run_diagnostic(
            [status.binary_path, "--help"],
            timeout_seconds=timeout_seconds,
        )
        if binary_result[0] not in {0, 1, 2}:
            return RuntimeTestResult(
                "dependency_error",
                "crawlergo 可执行文件无法完成安全诊断启动。",
            )
        chrome_version = ""
        if status.chrome_path:
            chrome_result = self._run_diagnostic(
                [status.chrome_path, "--version"],
                timeout_seconds=timeout_seconds,
            )
            if chrome_result[0] == 0:
                chrome_version = _first_line(chrome_result[1])
        return RuntimeTestResult(
            "enabled",
            f"运行时诊断通过。{CRAWLERGO_SAFETY_NOTE}",
            binary_version="crawlergo help 可启动",
            chrome_version=chrome_version,
        )

    def terminate_all(self) -> None:
        with self._lock:
            processes = list(self._processes)
        for process in processes:
            if process.poll() is not None:
                continue
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        with self._lock:
            self._processes.clear()

    def _run_diagnostic(
        self,
        command: list[str],
        *,
        timeout_seconds: int,
    ) -> tuple[int, str, str]:
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
                creationflags=_hidden_window_flag(),
            )
        except OSError:
            return -1, "", ""
        with self._lock:
            self._processes.add(process)
        try:
            stdout, stderr = process.communicate(timeout=max(1, timeout_seconds))
            return process.returncode, stdout[:2_000], stderr[:2_000]
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=2)
            return -1, stdout[:2_000], stderr[:2_000]
        finally:
            with self._lock:
                self._processes.discard(process)

    def _status_for_paths(
        self,
        mode: str,
        binary: Path,
        chrome: Path | None,
        *,
        bundled: bool = False,
    ) -> CrawlergoRuntimeStatus:
        if not chrome:
            return CrawlergoRuntimeStatus(
                state="dependency_missing",
                mode=mode,
                binary_path=str(binary),
                binary_status="available",
                chrome_status="missing",
                configured=True,
                bundled=bundled,
                message="已找到 crawlergo，但未找到 Chrome / Chromium。",
            )
        return CrawlergoRuntimeStatus(
            state="enabled",
            mode=mode,
            binary_path=str(binary),
            chrome_path=str(chrome),
            binary_status="available",
            chrome_status="available",
            configured=True,
            bundled=bundled,
            message=f"已发现 {mode} crawlergo 与浏览器运行时。{CRAWLERGO_SAFETY_NOTE}",
        )

    def _bundled_binary_candidates(self) -> list[Path]:
        return [
            self.app_dir / "runtime" / "crawlergo" / "crawlergo.exe",
            self.app_dir / "crawlergo" / "crawlergo.exe",
        ]

    def _bundled_chrome_candidates(self) -> list[Path]:
        return [
            self.app_dir / "runtime" / "chromium" / "chrome.exe",
            self.app_dir / "chromium" / "chrome.exe",
        ]

    def _system_chrome_candidates(self) -> list[Path]:
        candidates = [
            Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
            Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
            Path("C:/Program Files/Chromium/Application/chrome.exe"),
            Path("C:/Program Files (x86)/Chromium/Application/chrome.exe"),
            Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
            Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        ]
        return candidates

    def _bundled_license_ready(self) -> bool:
        notices = self.app_dir / "THIRD_PARTY_NOTICES.md"
        license_file = self.app_dir / "third_party" / "licenses" / "crawlergo-LICENSE.txt"
        source_offer = self.app_dir / "third_party" / "crawlergo-SOURCE.md"
        return notices.is_file() and license_file.is_file() and source_offer.is_file()


def build_crawlergo_command(
    binary_path: str,
    chrome_path: str,
    seed_url: str,
    policy: CrawlPolicy,
    *,
    resolver: Any | None = None,
) -> CrawlergoCommand:
    binary = _require_file(binary_path, "crawlergo")
    chrome = _require_file(chrome_path, "Chrome / Chromium")
    safety = validate_crawl_url(
        seed_url,
        allowed_domains=policy.allowed_domains,
        blocked_domains=policy.blocked_domains,
        dev_mode=policy.dev_allow_localhost,
        resolver=resolver,
    )
    if not safety.allowed:
        raise ValueError(safety.reason)
    command = [
        str(binary),
        "-c",
        str(chrome),
        "--output-mode",
        "json",
        "--max-crawled-count",
        str(policy.max_pages_per_domain),
        "--max-tab-count",
        "1",
        "--tab-run-timeout",
        str(policy.timeout_seconds),
        "--max-run-time",
        str(policy.timeout_seconds),
        safety.normalized_url,
    ]
    return CrawlergoCommand(
        command=command,
        allowed_domains=list(policy.allowed_domains),
        max_depth=policy.max_depth,
        timeout_seconds=policy.timeout_seconds,
    )


def _application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def _validated_file(value: str | Path) -> Path | None:
    if not value:
        return None
    try:
        path = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return path if path.is_file() else None


def _first_file(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        result = _validated_file(candidate)
        if result:
            return result
    return None


def _which_file(names: tuple[str, ...]) -> Path | None:
    for name in names:
        value = shutil.which(name)
        result = _validated_file(value or "")
        if result:
            return result
    return None


def _require_file(value: str, label: str) -> Path:
    result = _validated_file(value)
    if not result:
        raise ValueError(f"{label} 路径不存在或不是文件。")
    return result


def _first_line(value: str) -> str:
    return next((line.strip() for line in value.splitlines() if line.strip()), "")[:300]


def _hidden_window_flag() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
