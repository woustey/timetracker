"""Theming (PRD-02 §8.4, FR-701): Fusion style + a light or dark palette, one QSS string.

``system`` follows ``QStyleHints.colorScheme()`` live; ``light``/``dark`` are
manual overrides. No third-party theme package.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

ACCENT = "#2f80ed"
DANGER = "#e5484d"


def _palette(dark: bool) -> QPalette:
    p = QPalette()
    if dark:
        window, base, alt, text, disabled = "#202124", "#2a2b2e", "#26272a", "#e8eaed", "#7c7f85"
        button, mid, highlight_text = "#33353a", "#4a4d54", "#ffffff"
    else:
        window, base, alt, text, disabled = "#f3f4f6", "#ffffff", "#f7f8fa", "#1f2329", "#9aa0a6"
        button, mid, highlight_text = "#e9ebef", "#c9cdd3", "#ffffff"
    p.setColor(QPalette.ColorRole.Window, QColor(window))
    p.setColor(QPalette.ColorRole.WindowText, QColor(text))
    p.setColor(QPalette.ColorRole.Base, QColor(base))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(alt))
    p.setColor(QPalette.ColorRole.Text, QColor(text))
    p.setColor(QPalette.ColorRole.Button, QColor(button))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(text))
    p.setColor(QPalette.ColorRole.Mid, QColor(mid))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(disabled))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(base))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(text))
    p.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(highlight_text))
    p.setColor(QPalette.ColorRole.Link, QColor(ACCENT))
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.WindowText,
    ):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(disabled))
    return p


def _qss(dark: bool) -> str:
    return f"""
QToolTip {{ border: 1px solid palette(mid); padding: 4px; }}
QPushButton {{
    padding: 5px 12px; border: 1px solid palette(mid); border-radius: 6px;
    background: palette(button);
}}
QPushButton:default {{ border-color: {ACCENT}; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:focus {{ border: 2px solid {ACCENT}; }}
QPushButton:disabled {{ color: palette(placeholder-text); }}
QLineEdit, QComboBox, QDateEdit, QTimeEdit, QTextEdit, QSpinBox {{
    border: 1px solid palette(mid); border-radius: 5px; padding: 3px 6px; background: palette(base);
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus, QTextEdit:focus,
QSpinBox:focus {{
    border: 2px solid {ACCENT};
}}
QToolButton:focus {{ border: 2px solid {ACCENT}; border-radius: 6px; }}
QLineEdit[error="true"] {{ border: 2px solid {DANGER}; }}
QHeaderView::section {{
    padding: 4px; border: none; border-bottom: 1px solid palette(mid); background: palette(window);
}}
QTableView {{ gridline-color: palette(mid); selection-background-color: {ACCENT}; }}
QStatusBar {{ border-top: 1px solid palette(mid); }}
#popover {{ background: palette(window); border: 1px solid palette(mid); border-radius: 8px; }}
#toast {{ background: {"#3a3d44" if dark else "#1f2329"}; color: #ffffff; border-radius: 8px; }}
#toast QLabel {{ color: #ffffff; }}
#toast QPushButton {{ color: #9ec5ff; border: none; background: transparent; font-weight: 600; }}
"""


class ThemeManager(QObject):
    """Applies the chosen theme and follows the OS when set to ``system``."""

    def __init__(self, app: QApplication, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._app = app
        self._mode = "system"
        app.setStyle(QStyleFactory.create("Fusion"))
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._on_scheme_changed)

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_dark(self) -> bool:
        if self._mode == "dark":
            return True
        if self._mode == "light":
            return False
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark

    def apply(self, mode: str) -> None:
        self._mode = mode if mode in ("system", "light", "dark") else "system"
        dark = self.is_dark
        self._app.setPalette(_palette(dark))
        self._app.setStyleSheet(_qss(dark))

    def _on_scheme_changed(self, _scheme: object) -> None:
        if self._mode == "system":
            self.apply("system")
