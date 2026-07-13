from __future__ import annotations

import sys
from pathlib import Path


def _self_test_sqlite() -> int:
    try:
        import _sqlite3
        import sqlite3

        connection = sqlite3.connect(":memory:")
        try:
            runtime_version = connection.execute("select sqlite_version()").fetchone()[0]
            connection.execute("CREATE VIRTUAL TABLE self_test_fts USING fts5(title, body)")
            connection.execute(
                "INSERT INTO self_test_fts(title, body) VALUES (?, ?)",
                ("Company Decision Monitor", "SQLite FTS5 frozen runtime test"),
            )
            fts_row = connection.execute(
                "SELECT title FROM self_test_fts WHERE self_test_fts MATCH ?",
                ("frozen",),
            ).fetchone()
            if not fts_row or fts_row[0] != "Company Decision Monitor":
                raise RuntimeError("FTS5 in-memory query returned no result")
        finally:
            connection.close()

        index_path = _bundled_symbol_index_path()
        if not index_path.exists():
            raise FileNotFoundError(f"bundled symbol index not found: {index_path}")
        index = sqlite3.connect(f"{index_path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            objects = {
                str(row[0]): str(row[1])
                for row in index.execute(
                    "SELECT name, type FROM sqlite_master WHERE name IN (?, ?, ?, ?)",
                    ("symbols", "aliases", "symbols_fts", "symbol_universe"),
                )
            }
            if objects.get("symbols") != "table" or objects.get("aliases") != "table":
                raise RuntimeError("bundled symbol index is missing symbols or aliases")
            if "symbols_fts" not in objects and objects.get("symbol_universe") != "view":
                raise RuntimeError("bundled symbol index is missing FTS5 table or compatibility view")

            exact = index.execute(
                "SELECT symbol FROM symbols WHERE normalized_symbol = ? LIMIT 1", ("AAPL",)
            ).fetchone()
            prefix = index.execute(
                "SELECT symbol FROM symbols WHERE normalized_name >= ? AND normalized_name < ? LIMIT 1",
                ("apple", "apple\uffff"),
            ).fetchone()
            alias = index.execute(
                """
                SELECT s.symbol FROM symbols s
                JOIN aliases a ON a.symbol_id = s.id
                WHERE a.normalized_alias = ? LIMIT 1
                """,
                ("aapl",),
            ).fetchone()
            if not exact or not prefix or not alias:
                raise RuntimeError("bundled symbol index exact/prefix/alias query failed")
            if "symbols_fts" in objects:
                fts = index.execute(
                    "SELECT symbol FROM symbols_fts WHERE symbols_fts MATCH ? LIMIT 1",
                    ('"apple"*',),
                ).fetchone()
                if not fts:
                    raise RuntimeError("bundled symbol index FTS query failed")
        finally:
            index.close()
    except Exception as exc:
        print(f"SQLite self-test failed: {exc}", file=sys.stderr)
        return 1

    extension_path = getattr(_sqlite3, "__file__", "unknown")
    print(
        "SQLite self-test passed: "
        f"stdlib={sqlite3.sqlite_version}, runtime={runtime_version}, extension={extension_path}, "
        f"fts5=ok, index=ok, index_path={index_path}"
    )
    return 0


def _bundled_symbol_index_path() -> Path:
    package_path = Path(__file__).resolve().parent / "resources" / "symbol_universe" / "symbol_universe.sqlite"
    if package_path.exists():
        return package_path
    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        return Path(bundle_root) / "cdm_desktop" / "resources" / "symbol_universe" / "symbol_universe.sqlite"
    return package_path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--self-test", "sqlite"]:
        return _self_test_sqlite()

    from cdm_desktop.app import create_qapplication
    from cdm_desktop.logging_config import configure_logging
    from cdm_desktop.paths import get_app_paths
    from cdm_desktop.ui.main_window import MainWindow

    paths = get_app_paths()
    configure_logging(paths)

    app = create_qapplication(sys.argv)
    window = MainWindow(paths)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
