from __future__ import annotations

from pathlib import Path


def main() -> int:
    cache_root = Path.cwd() / ".test_runtime"
    if cache_root.exists():
        for child in cache_root.iterdir():
            if child.is_dir():
                print(f"Cache directory present: {child}")
    print("Public + Free API Network Mode: use the Settings page to clear public API cache.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
