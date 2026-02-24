# JM Studio Flatpak

Flatpak packaging for [JM Studio](https://www.creality.com/) (Creality 3D scanner software), running on Linux via a custom Wine build with USB and UVC camera support.

## Custom Wine Patches

This Flatpak bundles a custom Wine fork that includes:

- **wineusb0.sys** — Kernel driver bridging libusb-win32 IOCTLs to Linux libusb
- **qcap V4L2 camera support** — DirectShow capture using V4L2, including IAMVideoProcAmp and IAMCameraControl
- UVC Extension Unit (XU) query support for scanner control

## Building

Install the Flatpak SDK and runtime:

```bash
flatpak install flathub org.freedesktop.Platform//24.08 org.freedesktop.Sdk//24.08
```

Build and install locally:

```bash
flatpak-builder --user --install --force-clean build-dir com.creality.JMStudio.yaml
```

## Running

```bash
flatpak run com.creality.JMStudio
```

## USB Device Access

Users need a udev rule granting access to the Creality scanner. Create `/etc/udev/rules.d/99-creality-scanner.rules`:

```
SUBSYSTEM=="usb", ATTR{idVendor}=="1d6b", MODE="0666"
```

Then reload:

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## License

The Wine patches are licensed under LGPL-2.1+, consistent with upstream Wine.
JM Studio is proprietary software by Creality.
