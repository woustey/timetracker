# Release checklist

PRD-02 §11 says the platform behaviour "cannot be automated cheaply" — this is
the written checklist per release. Tick every line on each OS you ship for.

## 0. Before tagging

- [ ] `pytest` green locally and CI green on the three OSes
- [ ] `pyproject.toml` version bumped; `docs/RELEASE-NOTES.md` updated
- [ ] `python scripts/make_icons.py` if the artwork changed
- [ ] **Dry-run the release build first**: *Actions › Release › Run workflow* on
      `main` (`gh workflow run release.yml --ref main`). It builds and smoke-tests
      all three platforms and skips publishing because there is no tag. Only tag
      when it is green — 1.0.0 needed three rounds for bugs a local Windows build
      cannot show (a Windows-only dependency passed to Nuitka on every OS, the
      binary colliding with the `timetracker/` data directory on case-sensitive
      systems, shell scripts committed without the executable bit)
- [ ] Tag `vX.Y.Z` → the *Release* workflow builds the Windows installer + portable zip,
      the macOS DMG and the Linux AppImage + tar.gz, and publishes a GitHub Release

## 1. Clean install (fresh VM or Windows Sandbox)

- [ ] Installer runs without elevation; Start Menu (and optional Desktop) shortcut present
- [ ] First launch: tray icon appears; welcome dialog; clients typed become chips;
      the popover opens by itself
- [ ] **First entry recorded within 60 s, no documentation** (NFR-09) — time it
- [ ] Cold start ≤ 2 s (NFR-01): `TIMETRACKER_MEASURE_BOOT=5 timetracker.exe` prints it
- [ ] Uninstall leaves the data folder in place

## 2. Tray and popover

- [ ] Icon legible on light and dark taskbars; three states visible (idle / running / attention)
- [ ] Left-click → popover, anchored to the icon, never off-screen (test a second monitor
      and a vertical taskbar); Esc and click-outside dismiss it
- [ ] Right-click → native menu: Start/Stop, Add Time…, Open log…, Settings…, Quit
- [ ] Tooltip shows elapsed · type · client while running
- [ ] Quit with a running timer asks: Stop and save / Keep running / Discard

## 3. Timer trust

- [ ] `kill -9` (Task Manager › End task) mid-timer, relaunch → recovery offer ≤ 30 s short
- [ ] Sleep the machine ≥ 10 min with a timer running → "You were away" on wake with the
      right duration; each of the four outcomes does what it says
- [ ] Lock screen ≥ idle threshold → the same prompt ("No input for …")
- [ ] Change the system clock during a timer → duration unaffected; warning in the log

## 4. Add Time

- [ ] tray → `+30min` → `Add` = 3 clicks with sticky labels; toast with Undo
- [ ] Keyboard: digits, QWERT/ASDFG, Tab → note, Enter, Ctrl+Z, Esc — on **this** keyboard layout
- [ ] Typing a near-duplicate client offers the existing one

## 5. Log and export

- [ ] Filters, search, sort, inline edit, delete + undo
- [ ] Export XLSX opens in Excel: header frozen, durations sum, *Export info* sheet
- [ ] Export while the target file is open in Excel → "Choose another name…"

## 6. Settings

- [ ] Start at login toggles the OS login item (check the Run key / LaunchAgent / autostart entry)
- [ ] Theme: system / light / dark, live
- [ ] Idle row shows the provider name, or the reason it is unavailable (Wayland!)
- [ ] Back up now → file appears; Restore → app restarts with the restored data

## 7. Accessibility (NFR/§9.5)

- [ ] Every surface fully operable with Tab / Space / Enter
- [ ] Screen reader (Narrator / VoiceOver / Orca) announces chips with name and selected state
- [ ] 200 % display scaling: nothing clipped

## 8. Signing (§12.3) — before distributing beyond your own machines

Unsigned binaries trigger SmartScreen ("Windows protected your PC") and Gatekeeper
("cannot be opened because the developer cannot be verified"). Budget for:

- **Windows**: an Authenticode certificate (OV or EV; EV avoids the SmartScreen
  reputation ramp). Sign `timetracker.exe` *and* the installer with `signtool`.
- **macOS**: an Apple Developer ID; codesign the `.app` with hardened runtime,
  notarize the DMG with `notarytool`, staple.
- Until then, document the workaround in the README (it is there now).

## 9. Licence compliance (§12.4)

PySide6/Qt is LGPLv3. Shipping a closed-source binary is allowed **if** the user can
replace Qt: Nuitka `--standalone` keeps Qt as dynamic libraries in the output folder —
verify after each build that `Qt6*.dll` / `Qt*.framework` / `libQt6*.so` are separate
files (they are; `THIRD_PARTY_NOTICES.md` explains how to swap them). Ship the LGPL
text and the source offer (both in `THIRD_PARTY_NOTICES.md`). This project itself is
MIT, so the obligation is met by keeping those files in the bundle.
