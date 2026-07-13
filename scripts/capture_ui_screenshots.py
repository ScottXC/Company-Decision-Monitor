from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402

from cdm_desktop.app import create_qapplication  # noqa: E402
from cdm_desktop.paths import AppPaths  # noqa: E402
from cdm_desktop.ui.main_window import MainWindow  # noqa: E402
from cdm_desktop.ui.theme import ThemeManager  # noqa: E402

OUTPUT = ROOT / "reports" / "ui_screenshots"


def _paths(root: Path) -> AppPaths:
    return AppPaths(
        app_data_dir=root,
        logs_dir=root / "logs",
        raw_documents_dir=root / "raw_documents",
        exports_dir=root / "exports",
        cache_dir=root / "cache",
        db_path=root / "cdm.db",
    ).ensure()


def _capture(app, window: MainWindow, name: str) -> None:
    app.processEvents()
    pixmap = window.grab()
    image = QImage(window.size(), QImage.Format.Format_RGB32)
    manager = ThemeManager.instance()
    image.fill(QColor("#0d100e" if manager and manager.resolved_theme() == "dark" else "#f7f8f7"))
    painter = QPainter(image)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    target = OUTPUT / name
    if not image.save(str(target)):
        raise RuntimeError(f"Could not save UI screenshot: {target}")
    print(
        f"Captured {target} ({image.width()}x{image.height()}, "
        f"native_dpr={pixmap.devicePixelRatio():.2f})"
    )


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    app = create_qapplication(["capture-ui"])
    manager = ThemeManager.instance()
    if manager is None:
        raise RuntimeError("ThemeManager was not installed")

    with tempfile.TemporaryDirectory(prefix="cdm-ui-capture-") as temp_dir:
        window = MainWindow(_paths(Path(temp_dir)))
        window.resize(1440, 900)
        window.show()

        manager.apply("light", persist=False)
        window.navigate("/dashboard")
        _capture(app, window, "dashboard-light.png")

        window.navigate("/search")
        window.search_page.input.clear()
        window.search_page._clear_results()
        window.search_page._show_initial_state()
        _capture(app, window, "search-initial-light.png")

        response = window.search_page.service.search_local("AAPL", use_cache=False)
        window.search_page.input.blockSignals(True)
        window.search_page.input.setText("AAPL")
        window.search_page.input.blockSignals(False)
        window.search_page._render_response(response)
        _capture(app, window, "search-results-light.png")

        company = response.companies[0]
        window.company_detail_page._load_related = lambda: None  # type: ignore[method-assign]
        window.company_detail_page.set_company(company)
        window.navigate("/company/placeholder")
        _capture(app, window, "company-detail-light.png")

        manager.apply("dark", persist=False)
        _capture(app, window, "company-detail-dark.png")

        manager.apply("light", persist=False)
        window.watchlist_page.watchlist.add(company)
        window.navigate("/watchlist")
        _capture(app, window, "watchlist-light.png")

        window.navigate("/settings")
        _capture(app, window, "settings-light.png")
        manager.apply("dark", persist=False)
        _capture(app, window, "settings-dark.png")

        manager.apply("dark", persist=False)
        window.navigate("/dashboard")
        _capture(app, window, "dashboard-dark.png")
        window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
