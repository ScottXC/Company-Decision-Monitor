from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
ARTIFACTS = [
    ROOT / "dist" / "CompanyDecisionMonitor" / "CompanyDecisionMonitor.exe",
    ROOT / "dist" / "CompanyDecisionMonitor_Portable.zip",
    ROOT / "dist" / "installer" / "CompanyDecisionMonitor_Setup.exe",
]


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    rows = []
    failures = []
    for path in ARTIFACTS:
        if not path.exists():
            failures.append(f"Missing artifact: {path}")
            continue
        digest = _sha256(path)
        rows.append(
            {
                "name": path.name,
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": digest,
            }
        )

    report = {"artifacts": rows, "failures": failures}
    report_path = REPORTS / "release_hashes.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        return 1

    print("SHA256 release artifact hashes")
    print("| Artifact | Size MB | SHA256 |")
    print("|---|---:|---|")
    for row in rows:
        print(f"| {row['name']} | {row['size_bytes'] / 1024 / 1024:.1f} | `{row['sha256']}` |")
    print()
    print("Markdown for GitHub Release:")
    for row in rows:
        print(f"- `{row['name']}` SHA256: `{row['sha256']}`")
    print(f"\nReport: {report_path}")
    return 0


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


if __name__ == "__main__":
    sys.exit(main())
