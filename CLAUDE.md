# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Flatpak (`io.github.poita66.jmstudio`) that runs JM Studio, the proprietary 3DMakerPro / Creality
CR-Scan Lizard scanner software, on Wine 11.20 with patches for camera control (qcap, V4L2, UVC
extension units) and libusb-win32 scanners (wineusb0.sys). JM Studio is not shipped; the launcher
installs it from the user's downloaded installer on first run. User-facing docs are in `README.md`;
protocol findings, measurements and open items are in `NOTES.md` (read it first, update it when
something new is learned).

## Build and run

```bash
flatpak-builder --user --install --force-clean --ccache build-dir io.github.poita66.jmstudio.yaml
flatpak run io.github.poita66.jmstudio
```

## Layout

- `io.github.poita66.jmstudio.yaml` - manifest: upstream `wine-11.20.tar.xz` (sha256-pinned,
  GPG-signed upstream) plus `patches/wine/*.patch`, Wine Mono 11.3.0, and the launcher.
  `--allow=multiarch` is required (without `modify_ldt` wineboot leaves syswow64 empty).
  `CROSSCFLAGS=-O2` keeps DWARF out of the PE DLLs (1.8 GB -> ~1 GB).
- `patches/wine/` - the complete delta from upstream Wine, exported from the fork. Regenerate with
  `git -C <poita66/wine checkout> format-patch --no-signature -o patches/wine wine-11.20..rebase/wine-11.20`
  after deleting the old files, then update the `paths:` list in the manifest. Patch changes are
  made in the fork, never by editing these files.
- `jmstudio.sh` - launcher: prefix in `$XDG_DATA_HOME/prefix`, first-run install from
  `~/Downloads/JMStudio*.exe` or an argument, `WINEDLLOVERRIDES=mshtml=` (Mono is bundled).
- `tools/` - stdlib Python: native V4L2 capture (`lizard_capture.py`), usbmon readers, and
  `qcap_read_test.py` (Wine qcap's libv4l2 read path; run it inside the Flatpak from
  `~/.var/app/io.github.poita66.jmstudio/data/`, the sandbox cannot see the repo).
- `calibration/` - per-scanner calibration downloaded by JM Studio (byte-exact, `-text`).
- `logs/` - JM Studio logs from earlier installs, account email redacted.

## Conventions

- Wine source of truth is the fork `poita66/wine`, branch `rebase/wine-11.20` (local worktree at
  `~/Repos/Vendor/wine-11.20`). Wine-style commit subjects (`module: Do thing.`).
- Host-side settings a Flatpak cannot make (udev rules for USB permissions and autosuspend) go in
  the README's host setup section.
- Wine patches are LGPL-2.1-or-later; JM Studio is proprietary and never committed.
