"""Shared fixtures.

The socket audit hook is installed at import time — before any ``QApplication``
exists — so that :mod:`tests.test_no_network` can assert that nothing in the whole
test process, application boot included, touched the socket layer.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SOCKET_EVENTS: list[tuple[str, tuple[Any, ...]]] = []


def _audit(event: str, args: tuple[Any, ...]) -> None:
    if event.startswith("socket."):
        SOCKET_EVENTS.append((event, args))


sys.addaudithook(_audit)


@pytest.fixture(scope="session")
def qapp_cls() -> type:
    """Make pytest-qt's ``qapp`` fixture an instance of our ``App`` subclass."""
    from timetracker.app import App

    return App
