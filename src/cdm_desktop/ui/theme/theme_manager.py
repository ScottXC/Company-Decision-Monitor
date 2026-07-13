from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtWidgets import QApplication


class ThemeManager(QObject):
    theme_changed = Signal(str)
    _instance: ThemeManager | None = None

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self.app = app
        self.settings = QSettings("CompanyDecisionMonitor", "CompanyDecisionMonitor")
        self.preference = str(self.settings.value("ui/theme", "system"))
        if self.preference not in {"light", "dark", "system"}:
            self.preference = "system"

    @classmethod
    def install(cls, app: QApplication) -> ThemeManager:
        cls._instance = cls(app)
        cls._instance.apply(cls._instance.preference, persist=False)
        return cls._instance

    @classmethod
    def instance(cls) -> ThemeManager | None:
        return cls._instance

    def resolved_theme(self) -> str:
        if self.preference != "system":
            return self.preference
        try:
            scheme = self.app.styleHints().colorScheme()
            return "dark" if scheme == Qt.ColorScheme.Dark else "light"
        except AttributeError:
            return "light"

    def apply(self, preference: str, *, persist: bool = True) -> None:
        if preference not in {"light", "dark", "system"}:
            preference = "system"
        self.preference = preference
        if persist:
            self.settings.setValue("ui/theme", preference)
        resolved = self.resolved_theme()
        path = Path(__file__).resolve().parent / f"{resolved}.qss"
        self.app.setStyleSheet(path.read_text(encoding="utf-8"))
        self.app.setProperty("cdmTheme", resolved)
        self.theme_changed.emit(resolved)

    def toggle(self) -> str:
        target = "light" if self.resolved_theme() == "dark" else "dark"
        self.apply(target)
        return target
