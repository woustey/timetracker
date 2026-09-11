from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from timetracker.crashlog import LOG_NAME

_CRASH = """
import sys
from pathlib import Path
from timetracker import crashlog
crashlog.install(Path(sys.argv[1]))
raise RuntimeError("boom-from-test")
"""


def test_uncaught_exception_lands_in_the_log_file(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", _CRASH, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    assert "boom-from-test" in result.stderr  # the previous hook still runs
    text = (tmp_path / LOG_NAME).read_text(encoding="utf-8")
    assert "CRITICAL timetracker: Unhandled exception" in text
    assert "RuntimeError: boom-from-test" in text


def test_install_is_idempotent(tmp_path: Path) -> None:
    import logging

    from timetracker import crashlog

    crashlog.install(tmp_path)
    crashlog.install(tmp_path)
    handlers = [h for h in logging.getLogger("timetracker").handlers if hasattr(h, "baseFilename")]
    assert len(handlers) == 1
    for h in handlers:
        h.close()
        logging.getLogger("timetracker").removeHandler(h)
