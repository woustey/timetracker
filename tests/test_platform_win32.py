"""``detach_orphan_console``: frees a console only when nobody else shares it.

The subprocess tests use the *base* interpreter (``sys._base_executable``): the
venv's ``python.exe`` is a redirector that would itself be attached to the new
console and skew the client count — which is exactly the behaviour under test.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from timetracker.platform.win32 import detach_orphan_console

win_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows console semantics")
SRC = Path(__file__).resolve().parents[1] / "src"

_PROBE = """
import ctypes, sys
from pathlib import Path
from timetracker.platform.win32 import detach_orphan_console
k = ctypes.windll.kernel32
before = k.GetConsoleWindow()
detached = detach_orphan_console()
after = k.GetConsoleWindow()
Path(sys.argv[1]).write_text(f"{before != 0} {detached} {after != 0}", encoding="utf-8")
"""

_PARENT = """
import subprocess, sys
subprocess.run([sys.executable, sys.argv[1], sys.argv[2]], check=True)
"""


def _base_python() -> str:
    return getattr(sys, "_base_executable", sys.executable)


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    return env


def test_noop_off_windows_or_when_shared() -> None:
    # Under pytest we share the console with the shell (or have none): never detach.
    assert detach_orphan_console() is False
    print("stdout still usable")


@win_only
def test_detaches_a_console_created_only_for_us(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text(_PROBE, encoding="utf-8")
    out = tmp_path / "result.txt"
    subprocess.run(
        [_base_python(), str(probe), str(out)],
        creationflags=subprocess.CREATE_NEW_CONSOLE,  # a fresh console with one client: us
        env=_env(),
        timeout=60,
        check=True,
    )
    assert out.read_text(encoding="utf-8") == "True True False"


@win_only
def test_keeps_a_console_shared_with_a_parent(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text(_PROBE, encoding="utf-8")
    parent = tmp_path / "parent.py"
    parent.write_text(_PARENT, encoding="utf-8")
    out = tmp_path / "result.txt"
    # The parent interpreter owns the new console and runs the probe inside it:
    # two clients → the probe must keep the console.
    subprocess.run(
        [_base_python(), str(parent), str(probe), str(out)],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        env=_env(),
        timeout=60,
        check=True,
    )
    assert out.read_text(encoding="utf-8") == "True False True"
