from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from cdm_desktop import PRODUCT_NAME_ZH, __version__


def create_qapplication(argv: list[str] | None = None) -> QApplication:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(argv or sys.argv)
    app.setApplicationName("Company Decision Monitor")
    app.setApplicationDisplayName(PRODUCT_NAME_ZH)
    app.setOrganizationName("CompanyDecisionMonitor")
    app.setApplicationVersion(__version__)
    qss_path = Path(__file__).resolve().parent / "ui" / "styles.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))
    return app
