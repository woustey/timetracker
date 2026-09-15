# Third-party notices

Time Tracker is MIT-licensed (see `LICENSE`). It bundles the following
third-party components in its release builds.

## Qt 6 and PySide6 — LGPL v3

Copyright © The Qt Company Ltd. and contributors. Licensed under the GNU Lesser
General Public License version 3 (<https://www.gnu.org/licenses/lgpl-3.0.html>).

The Qt libraries are dynamically linked and shipped as separate files
(`Qt6*.dll` on Windows, `Qt*.framework` on macOS, `libQt6*.so*` on Linux) inside
the application folder. You may replace them with your own build of the same
Qt major version, as the LGPL permits: build or obtain compatible Qt 6 libraries
and overwrite the files of the same name.

Source code for Qt and PySide6 is available from The Qt Company at
<https://download.qt.io/> and <https://code.qt.io/cgit/pyside/pyside-setup.git/>.
On request, the Time Tracker maintainer will provide the exact Qt/PySide6
sources corresponding to a release build (see the repository's issue tracker).

## openpyxl — MIT

Copyright © 2010 openpyxl. MIT licence.

## tzdata (Windows builds) — Apache License 2.0

The IANA Time Zone Database, packaged by the Python `tzdata` project.
Apache License 2.0; data is in the public domain.

## pyobjc-framework-Quartz (macOS builds) — MIT

Copyright © Ronald Oussoren and contributors. MIT licence.

## Python — PSF License

Python is © Python Software Foundation, under the PSF License Agreement.
