# JM Studio for Linux (Flatpak)

A Flatpak that runs [JM Studio](https://forum.jimumeta.com/home/help/download.html), the 3D scanner
software from 3DMakerPro (also used by Creality's CR-Scan Lizard), on a patched Wine.

JM Studio itself is proprietary and is **not** included. On first launch the app installs it into
its own Wine prefix from the installer you download from 3DMakerPro.

Tested with a Creality CR-Scan Lizard (ICT 100W) and JM Studio 2.6.17.0237 on Fedora 43: connect,
preview, brightness, both SLAM modes and scanning work.

## What's inside

- **Wine 11.20**, built from the upstream release tarball (signed by Alexandre Julliard) as a
  WoW64 build: one 64-bit build that also runs JM Studio's 32-bit installer, with no 32-bit
  runtime needed.
- **14 patches** in [`patches/wine/`](patches/wine/), the complete difference from upstream
  Wine. They add what JM Studio needs to see and drive the scanner's cameras:

  | Patches | Change |
  |---|---|
  | 0004-0006 | qcap: `IAMCameraControl` and the remaining `VideoProcAmp` properties mapped to V4L2 controls (exposure, gain) |
  | 0010-0011 | qcap: `IKsControl` passthrough to UVC extension units (the scanner's serial number is read this way) |
  | 0007-0008 | avicap32, devenum: USB VID/PID in capture device names, as on Windows, so JM Studio recognises the scanner |
  | 0012-0013 | mf: `MFEnumDeviceSources()` for video capture devices |
  | 0009, 0014 | wineusb0.sys: a libusb-win32 compatibility driver for scanners that use libusb, registered as a service |
  | 0001-0003 | vcomp: the OpenMP runtime-schedule flag; mfreadwrite: reject a NULL media source |

- **Wine Mono 11.3.0**, because parts of JM Studio are .NET (mixed-mode C++/CLI).
- A launcher, [`jmstudio.sh`](jmstudio.sh), that installs JM Studio on first run and then starts
  it.

## Host setup (once)

The Flatpak cannot change USB settings on the host, so add this udev rule:

```
# /etc/udev/rules.d/99-creality-scanner.rules
# Keep the cameras out of USB autosuspend: resuming delays the first frame past
# JM Studio's ~500 ms connect timeout, so the first connect after idle fails.
ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="bcdc", TEST=="power/control", ATTR{power/control}="on"
```

Scanners that JM Studio drives through libusb (via `wineusb0.sys`) also need access to the raw USB
device. The Lizard's cameras go through V4L2 instead, so it may not need this; that is untested:

```
SUBSYSTEM=="usb", ATTR{idVendor}=="bcdc", MODE="0666"
```

Then reload the rules and replug the scanner:

```bash
sudo udevadm control --reload-rules
```

## Install

Download `jmstudio-<version>.flatpak` from the
[latest release](https://github.com/poita66/jmstudio-flatpak/releases/latest) and install it. The
runtime and SDK extensions come from Flathub:

```bash
flatpak install --user jmstudio-v11.20-1.flatpak
```

### Build it yourself

You need `flatpak-builder` and the Flathub remote:

```bash
flatpak install --user flathub org.freedesktop.Sdk//25.08 org.freedesktop.Platform//25.08 \
    org.freedesktop.Sdk.Extension.mingw-w64//25.08
flatpak-builder --user --install --force-clean build-dir io.github.poita66.jmstudio.yaml
```

Wine takes a while to compile the first time.

## First run

1. Download the JM Studio installer (`JMStudioSetup-*.exe`) from
   [3DMakerPro](https://forum.jimumeta.com/home/help/download.html) into your Downloads folder.
2. Start **JM Studio** from your app menu, or run `flatpak run io.github.poita66.jmstudio`.
3. The installer opens. Click through it and keep the default install location.

The newest `JMStudio*.exe` in Downloads is used. To use a different file, pass its path:
`flatpak run io.github.poita66.jmstudio /path/to/JMStudioSetup.exe`.

The Wine prefix lives in `~/.var/app/io.github.poita66.jmstudio/data/prefix`. Deleting that
folder starts over from the first run.

## Verifying the build

Release bundles are built by the [Release workflow](.github/workflows/release.yml) on GitHub's
runners from a signed tag, with every action and the builder image pinned. Each bundle has a
build-provenance attestation that ties its sha256 to that workflow, this repository and the tagged
commit:

```bash
gh attestation verify jmstudio-v11.20-1.flatpak --repo poita66/jmstudio-flatpak
```

Release tags are signed with an SSH key registered on the `poita66` GitHub account as a signing
key, so GitHub shows them as Verified.

Every input is pinned in [`io.github.poita66.jmstudio.yaml`](io.github.poita66.jmstudio.yaml) by
sha256, and the only change to Wine is the patch files in this repository:

- **Wine**: `wine-11.20.tar.xz` from dl.winehq.org. Check it against its signature from Alexandre
  Julliard's key `DA23579A74D4AD9AF9D3F945CEFAC8EAAF17519D`:
  ```bash
  gpg --recv-keys DA23579A74D4AD9AF9D3F945CEFAC8EAAF17519D
  gpg --verify wine-11.20.tar.xz.sign wine-11.20.tar.xz
  ```
- **Patches**: `patches/wine/*.patch` is `git format-patch wine-11.20..rebase/wine-11.20` of
  [poita66/wine](https://github.com/poita66/wine), so you can read them here or compare them with
  that branch.
- **Wine Mono**: `wine-mono-11.3.0-x86.tar.xz`. Upstream publishes no signature; the sha256 matches
  both dl.winehq.org and the GitHub release's asset digest.

## Troubleshooting

**Lines or stripes across the camera image.** The scanner is losing USB packets on its way to the
computer, so each frame is missing some rows. Plug it into a different port, preferably directly
into the computer rather than through a hub or dock. See "Stripe artefacts" in
[NOTES.md](NOTES.md).

**The first connect fails and a retry works.** Add the autosuspend udev rule above.

**JM Studio's logs** are in
`~/.var/app/io.github.poita66.jmstudio/data/prefix/drive_c/users/$USER/AppData/Roaming/Jimuyida/JMStudio/log/`.

**More detail from Wine and the camera stack:**

```bash
flatpak run --env=WINEDEBUG=err+all,warn+qcap \
    --env=LIBV4L2_LOG_FILENAME=$HOME/.var/app/io.github.poita66.jmstudio/data/libv4l2.log \
    io.github.poita66.jmstudio 2> jmstudio-wine.log
```

## Scanner protocol and tools

[NOTES.md](NOTES.md) documents how JM Studio talks to the CR-Scan Lizard (two UVC cameras, exposure
and gain per brightness level, the extension-unit tunnel, where calibration comes from) and the
issues found while packaging. [`tools/`](tools/) has Python scripts for working without JM Studio:

- `lizard_capture.py`: capture frames from both cameras natively over V4L2.
- `usbmon_ctl.py`, `usbmon_iso.py`: log the scanner's USB control and isochronous traffic.
- `qcap_read_test.py`: repeat Wine qcap's camera read path to test stream starts.

## License

The Wine patches are LGPL-2.1-or-later, like Wine. JM Studio is proprietary and is not
distributed here.
