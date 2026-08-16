from __future__ import annotations

import argparse
import json
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cdm_desktop import RELEASE_LABEL  # noqa: E402
from cdm_desktop.paths import AppPaths  # noqa: E402
from cdm_desktop.public_api.robots_policy import RobotsPolicy  # noqa: E402
from cdm_desktop.public_api.web_evidence_models import CrawlPolicy  # noqa: E402
from cdm_desktop.public_api.web_fetcher import SafeWebFetcher  # noqa: E402
from cdm_desktop.services.web_evidence_service import WebEvidenceService  # noqa: E402

SEEDS = (
    ("company_homepage", "https://www.apple.com/"),
    ("investor_relations", "https://investor.apple.com/"),
    ("official_news", "https://www.apple.com/newsroom/"),
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bounded public Web Evidence smoke.")
    parser.add_argument(
        "--public-dns-validation",
        action="store_true",
        help=(
            "Resolve only the fixed smoke hosts through Cloudflare DNS-over-HTTPS and "
            "override DNS inside this validation process. This is for fake-IP/TUN test "
            "machines only and does not change application SSRF policy."
        ),
    )
    return parser.parse_args()


def _public_dns_mapping(hosts: set[str]) -> dict[str, tuple[str, ...]]:
    mapping: dict[str, tuple[str, ...]] = {}
    with httpx.Client(timeout=15, follow_redirects=True) as client:
        for host in sorted(hosts):
            response = client.get(
                "https://cloudflare-dns.com/dns-query",
                params={"name": host, "type": "A"},
                headers={"Accept": "application/dns-json"},
            )
            response.raise_for_status()
            addresses = tuple(
                str(answer.get("data") or "")
                for answer in response.json().get("Answer", [])
                if answer.get("type") == 1 and answer.get("data")
            )
            if not addresses:
                raise RuntimeError(f"Public DNS returned no IPv4 address for {host}")
            mapping[host] = addresses
    return mapping


def _mapped_getaddrinfo(
    mapping: dict[str, tuple[str, ...]],
    fallback: Any,
):  # type: ignore[no-untyped-def]
    def resolve(
        host: str,
        port: object,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[tuple[object, ...]]:
        normalized = str(host).casefold().rstrip(".")
        addresses = mapping.get(normalized)
        if not addresses or family not in {0, socket.AF_INET}:
            return fallback(host, port, family, type, proto, flags)
        socket_type = type or socket.SOCK_STREAM
        protocol = proto or socket.IPPROTO_TCP
        return [
            (socket.AF_INET, socket_type, protocol, "", (address, port or 0))
            for address in addresses
        ]

    return resolve


class RecordingFetcher(SafeWebFetcher):
    def __init__(self) -> None:
        super().__init__(timeout_seconds=30)
        self.statuses: dict[str, int] = {}

    def fetch(self, url: str, **kwargs):  # type: ignore[no-untyped-def]
        response, error = super().fetch(url, **kwargs)
        if response is not None:
            self.statuses[url] = response.status_code
        return response, error


def _paths(root: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=root,
        logs_dir=root / "logs",
        raw_documents_dir=root / "raw_documents",
        exports_dir=root / "exports",
        cache_dir=root / "cache",
        db_path=root / "cdm.db",
    ).ensure()


def main() -> int:
    args = _arguments()
    dns_mode = "native_production_resolver"
    original_getaddrinfo = socket.getaddrinfo
    if args.public_dns_validation:
        hosts = {
            (urlsplit(seed).hostname or "").casefold().rstrip(".")
            for _content_type, seed in SEEDS
        }
        mapping = _public_dns_mapping(hosts)
        socket.getaddrinfo = _mapped_getaddrinfo(mapping, original_getaddrinfo)
        dns_mode = "process_local_cloudflare_doh"

    records: list[dict[str, object]] = []
    passed = True
    with tempfile.TemporaryDirectory(prefix="cdm-web-evidence-smoke-") as temp_dir:
        fetcher = RecordingFetcher()
        robots = RobotsPolicy(fetcher)
        service = WebEvidenceService(
            _paths(Path(temp_dir)),
            fetcher=fetcher,
            robots_policy=robots,
        )
        policy = CrawlPolicy(
            max_pages_per_domain=1,
            max_depth=0,
            request_delay_seconds=1,
            timeout_seconds=30,
        )
        for expected_type, seed in SEEDS:
            host = (urlsplit(seed).hostname or "").casefold().strip(".")
            robots_decision = robots.can_fetch(
                seed,
                allowed_domains=[host],
                blocked_domains=policy.blocked_domains,
            )
            started = time.perf_counter()
            result = service.crawl(
                company_id="smoke:aapl",
                company_name="Apple Inc.",
                seed_urls=[seed],
                company_website="https://www.apple.com/",
                policy=policy,
            )
            elapsed = round(time.perf_counter() - started, 3)
            item = result.items[0] if result.items else None
            record = {
                "seed_url": seed,
                "robots_allowed": robots_decision.allowed,
                "robots_missing": robots_decision.missing_robots,
                "robots_url": robots_decision.robots_url,
                "http_status": fetcher.statuses.get(seed)
                or fetcher.statuses.get(seed.rstrip("/")),
                "final_url": item.final_url if item else "",
                "content_type": item.content_type if item else expected_type,
                "title": item.title if item else "",
                "cleaned_text_length": len(item.cleaned_text) if item else 0,
                "snippet_length": len(item.content_snippet) if item else 0,
                "elapsed_seconds": elapsed,
                "job_status": result.job.status,
                "pages_processed": result.job.pages_processed,
                "errors": result.skipped_urls,
            }
            records.append(record)
            passed = passed and robots_decision.allowed and item is not None

        cancelled = threading.Event()
        cancelled.set()
        cancelled_result = service.crawl(
            company_id="smoke:cancel",
            company_name="Apple Inc.",
            seed_urls=["https://www.apple.com/"],
            company_website="https://www.apple.com/",
            policy=policy,
            cancel_event=cancelled,
        )
        service.shutdown()
        passed = passed and cancelled_result.job.status == "cancelled"

    print(
        json.dumps(
            {
                "version": RELEASE_LABEL,
                "passed": passed,
                "network_validation_mode": dns_mode,
                "production_safety_relaxed": False,
                "limits": {
                    "max_pages_per_seed": 1,
                    "max_depth": 0,
                    "request_delay_seconds": 1,
                    "timeout_seconds": 30,
                },
                "records": records,
                "cancellation_result": cancelled_result.job.status,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
