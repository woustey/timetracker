"""NFR-05: the application makes no network connections, under any circumstance.

Two layers:

1. Static — no module under ``src/timetracker`` imports a networking module,
   Python or Qt. This is the real guarantee; Qt's C++ socket calls are invisible
   to Python, so the only way to be sure is to never import the modules.
2. Dynamic — a ``sys.addaudithook`` installed in ``conftest.py`` before Qt is
   initialised records every ``socket.*`` audit event. Booting the app in
   offscreen mode must leave that record empty.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.conftest import SOCKET_EVENTS

SRC = Path(__file__).resolve().parents[1] / "src" / "timetracker"

NETWORK_MODULES = (
    "socket",
    "ssl",
    "select",
    "selectors",
    "http",
    "urllib",
    "urllib3",
    "requests",
    "httpx",
    "aiohttp",
    "ftplib",
    "smtplib",
    "poplib",
    "imaplib",
    "nntplib",
    "telnetlib",
    "xmlrpc",
    "websockets",
    "PySide6.QtNetwork",
    "PySide6.QtNetworkAuth",
    "PySide6.QtWebSockets",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtRemoteObjects",
    "PySide6.QtHttpServer",
)


def _imported_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
            # ``from PySide6 import QtNetwork`` style
            names.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return names


@pytest.mark.parametrize("path", sorted(SRC.rglob("*.py")), ids=lambda p: str(p.relative_to(SRC)))
def test_no_network_imports(path: Path) -> None:
    offenders = [
        name
        for name in _imported_names(path)
        if any(name == mod or name.startswith(mod + ".") for mod in NETWORK_MODULES)
    ]
    assert not offenders, f"{path.relative_to(SRC)} imports {offenders}"


def test_app_boot_opens_no_sockets(booted_app) -> None:  # type: ignore[no-untyped-def]
    booted_app.processEvents()
    booted_app.timer_service.start()
    booted_app.processEvents()
    booted_app.timer_service.stop()
    booted_app.processEvents()
    assert SOCKET_EVENTS == [], f"socket activity observed: {SOCKET_EVENTS}"
