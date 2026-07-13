from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from cdm_desktop import PRODUCT_NAME_ZH, __version__
from cdm_desktop.ui.theme import ThemeManager


def create_qapplication(argv: list[str] | None = None) -> QApplication:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(argv or sys.argv)
    app.setApplicationName("Company Decision Monitor")
    app.setApplicationDisplayName(PRODUCT_NAME_ZH)
    app.setOrganizationName("CompanyDecisionMonitor")
    app.setApplicationVersion(__version__)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    ThemeManager.install(app)
    return app
