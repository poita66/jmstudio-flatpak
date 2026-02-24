# JM Studio Wine Runner for Bottles

Custom Wine runner for [JM Studio](https://www.3dmakerpro.com/) (3DMakerPro 3D scanner software) on Linux, designed for use with [Bottles](https://usebottles.com/).

This Wine build ([poita66/wine](https://github.com/poita66/wine), branch `test/all-prs`) includes patches for:
- **wineusb0.sys** — libusb-win32 IOCTL bridge for USB scanner access
- **qcap** — V4L2 camera capture support
- **UVC Extension Unit** queries

## Prerequisites

Build dependencies (Fedora):
```bash
sudo dnf builddep wine
sudo dnf install libusb1-devel
```

You also need [Bottles](https://flathub.org/apps/com.usebottles.bottles) installed (Flatpak recommended).

## Building the runner

```bash
./build-runner.sh
```

This clones the Wine fork, builds it in WoW64 mode (single 64-bit build that handles 32-bit Windows apps), and produces `wine-jmstudio.tar.gz`.

You can set `JOBS=N` to control parallelism (defaults to `nproc`).

## Installing the runner

Extract the tarball into the Bottles runners directory:

```bash
tar xzf wine-jmstudio.tar.gz -C ~/.var/app/com.usebottles.bottles/data/bottles/runners/
```

Restart Bottles so it picks up the new runner.

## Setting up the bottle

1. In Bottles, create a new bottle (or import `bottle.yml`)
2. Set the runner to **wine-jmstudio**
3. Set Windows version to **Windows 10**, architecture to **win64**
4. Add JM Studio's installer or `JMStudio.exe` as a program

## USB scanner access

Your user needs permission to access the USB scanner. Create a udev rule:

```bash
# /etc/udev/rules.d/99-3dmakerpro.rules
# Replace XXXX:YYYY with your scanner's USB vendor:product ID (check lsusb)
SUBSYSTEM=="usb", ATTR{idVendor}=="XXXX", ATTR{idProduct}=="YYYY", MODE="0666"
```

Then reload rules:
```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## License

Wine patches are LGPL-2.1+. JM Studio itself is proprietary.
