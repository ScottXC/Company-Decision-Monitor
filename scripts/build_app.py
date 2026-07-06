from __future__ import annotations

from build_windows import main as build_windows_main


def main() -> int:
    return build_windows_main()


if __name__ == "__main__":
    raise SystemExit(main())
