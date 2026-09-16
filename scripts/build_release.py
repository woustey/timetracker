"""Release build with Nuitka ``--standalone`` (PRD-02 §12.1).

    python scripts/build_release.py            # → dist/release/<platform>/…

Windows: ``dist/release/windows/timetracker.dist/timetracker.exe`` (no console).
macOS:   ``dist/release/macos/Time Tracker.app`` (LSUIElement — no Dock icon;
         the binary inside is ``Contents/MacOS/timetracker.bin``).
Linux:   ``dist/release/linux/timetracker.dist/timetracker.bin``.

Qt is dynamically linked and replaceable in the output (LGPL §4d, PRD-02 §12.4);
``docs/RELEASE-CHECKLIST.md`` has the verification step. Nothing here is
signed — see the checklist for what to buy before distributing widely.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
RES = SRC / "timetracker" / "resources"
# Compiled as a package (`--python-flag=-m` + the package directory), the way
# `python -m timetracker` runs it; Nuitka warns when given `__main__.py` alone.
ENTRY = SRC / "timetracker"


def version() -> str:
    import tomllib

    with open(ROOT / "pyproject.toml", "rb") as fh:
        return str(tomllib.load(fh)["project"]["version"])


def main() -> int:
    if sys.platform == "win32":
        platform_dir = "windows"
    elif sys.platform == "darwin":
        platform_dir = "macos"
    else:
        platform_dir = "linux"
    out = ROOT / "dist" / "release" / platform_dir
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    ver = version()

    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--python-flag=-m",
        "--assume-yes-for-downloads",
        "--enable-plugin=pyside6",
        # Package mode already compiles everything reachable by import; the
        # migrations are loaded by name (importlib over pkgutil), so only they
        # need forcing in.
        "--include-package=timetracker.data.migrations",
        "--include-package-data=timetracker.resources",
        "--include-package=openpyxl",  # lazy-imported, so Nuitka would not see it
        "--nofollow-import-to=pytest",
        "--output-dir=" + str(out),
        # The dist also holds the package-data directory `timetracker/`; on
        # macOS/Linux a binary of the same name would collide with it, so the
        # executable is `timetracker.bin` there (Nuitka's own convention).
        "--output-filename=" + ("timetracker" if sys.platform == "win32" else "timetracker.bin"),
        "--company-name=Time Tracker",
        "--product-name=Time Tracker",
        f"--product-version={ver}",
        f"--file-version={ver}",
        "--file-description=Tray-resident time tracker",
        "--copyright=MIT licence; Qt is LGPLv3 (see THIRD_PARTY_NOTICES.md)",
    ]
    if sys.platform == "win32":
        cmd += [
            # tzdata is a win32-only dependency (macOS/Linux use the system zoneinfo);
            # Nuitka refuses to include a package that is not installed.
            "--include-package=tzdata",  # Nuitka ships its zoneinfo files with it
            "--windows-console-mode=disable",
            f"--windows-icon-from-ico={RES / 'icon.ico'}",
        ]
    elif sys.platform == "darwin":
        cmd += [
            "--macos-create-app-bundle",
            "--macos-app-name=Time Tracker",
            "--macos-app-mode=background",  # LSUIElement: no Dock icon (PRD-02 §12.2)
            f"--macos-app-version={ver}",
            "--include-package=Quartz",
        ]
        icns = RES / "icon.icns"
        if icns.exists():
            cmd.append(f"--macos-app-icon={icns}")
    else:
        cmd += [f"--linux-icon={RES / 'icon.png'}"]
    cmd.append(str(ENTRY))

    print(" ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)

    # Nuitka names the folder after the entry package; give it a stable name.
    # On macOS it leaves both `timetracker.dist` and the `timetracker.app` bundle
    # built from it: the bundle is the product.
    candidates = sorted(out.iterdir(), key=lambda p: p.suffix != ".app")
    produced = next((p for p in candidates if p.name.endswith((".app", ".dist"))), None)
    if produced is None:
        print("no output produced", file=sys.stderr)
        return 1
    final = out / ("Time Tracker.app" if produced.suffix == ".app" else "timetracker.dist")
    if produced != final:
        produced.rename(final)
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md", "README.md"):
        src = ROOT / name
        if src.exists():
            target_dir = final / "Contents" / "Resources" if final.suffix == ".app" else final
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target_dir / name)
    print(f"built {final}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
