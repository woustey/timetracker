"""``QApplication`` subclass: wiring and lifecycle."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from timetracker import __version__
from timetracker.ui.tray import TrayIcon

_NO_TRAY_TEXT = (
    "Time Tracker lives in the system tray, and this desktop session does not "
    "provide one.\n\nA windowed fallback mode is planned; for now the application "
    "cannot start here."
)


class App(QApplication):
    def __init__(self, argv: list[str]) -> None:
        super().__init__(argv)
        self.setApplicationName("Time Tracker")
        self.setApplicationVersion(__version__)
        self.setOrganizationName("timetracker")
        # Otherwise closing any window kills a tray app (PRD-02 §8.1).
        self.setQuitOnLastWindowClosed(False)
        # Strong reference: the tray must outlive every local scope.
        self.tray: TrayIcon | None = None

    def bootstrap(self) -> bool:
        """Create the tray. Returns ``False`` if the app cannot run here (FR-110)."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(None, "No system tray available", _NO_TRAY_TEXT)
            return False
        self.tray = TrayIcon(self)
        self.tray.quit_requested.connect(self.quit)
        self.tray.show()
        return True
