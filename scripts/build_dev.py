"""Development bundle with PyInstaller ``--onedir`` (PRD-02 §12.1): builds in seconds.

    python scripts/build_dev.py   # → dist/dev/timetracker/

Never ``--onefile``: it unpacks on every launch and costs ~2 s of start-up.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
RES = SRC / "timetracker" / "resources"


def main() -> int:
    out = ROOT / "dist" / "dev"
    work = ROOT / "build" / "pyinstaller"
    shutil.rmtree(out, ignore_errors=True)
    sep = ";" if sys.platform == "win32" else ":"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--noconsole",
        "--name=timetracker",
        f"--paths={SRC}",
        f"--distpath={out}",
        f"--workpath={work}",
        f"--specpath={work}",
        f"--add-data={RES}{sep}timetracker/resources",
        "--collect-data=tzdata",
        "--hidden-import=openpyxl",
        "--hidden-import=timetracker.platform.win32",
        "--hidden-import=timetracker.platform.macos",
        "--hidden-import=timetracker.platform.linux",
    ]
    if sys.platform == "win32":
        cmd.append(f"--icon={RES / 'icon.ico'}")
    cmd.append(str(SRC / "timetracker" / "__main__.py"))
    print(" ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)
    print(f"built {out / 'timetracker'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
