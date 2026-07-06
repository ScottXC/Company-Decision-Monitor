from __future__ import annotations

from pathlib import Path


def main() -> int:
    cache_root = Path.cwd() / ".test_runtime"
    if cache_root.exists():
        for child in cache_root.iterdir():
            if child.is_dir():
                print(f"Cache directory present: {child}")
    print("UI Preview Mode: cache cleanup is a placeholder for future local UI cache.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
