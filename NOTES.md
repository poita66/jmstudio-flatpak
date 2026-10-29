# Notes

## CR-Scan Lizard wire protocol (reverse engineering, 2026-10-29)

Target: JM Studio 2.6.10.0192 under the custom Wine build, scanner `DeviceSN=CRSLnnnnnnn`.
Evidence types are marked: **[usb]** observed with usbmon, **[static]** read from disassembly or
decompilation of the shipped DLLs, **[inferred]** not yet confirmed on the wire.

### Device

- Two UVC 1.x cameras behind a hub, both bound to `uvcvideo` **[usb]**:
  - `bcdc:000a` "ICT CameraA", `bcdc:000b` "ICT CameraB" (iSerial `200901010001` on both).
  - Each: VC interface with Camera Terminal (ID 1), Processing Unit (ID 2), Extension Unit (ID 4,
    GUID `{1229a78c-47b4-4094-b0ce-db07386fb938}`, selectors 10 and 11), Output Terminal (ID 3).
  - Formats: MJPEG 640x480 and 1280x720; YUY2 640x480. Isochronous video endpoint 0x81.
- No serial/CH343 device enumerates, so the Lizard has no side channel beyond the two cameras
  (the shipped CH343/serial code serves other models) **[usb]**.
- JM Studio opens one camera per SLAM mode: CameraA only, or CameraA + CameraB **[user]**.
  With preview running, the process held only `/dev/video3` (CameraA) **[usb]**.

### Software stack (JMDeviceCore.dll, `JMScannerSDK::Lizard_ICT_100W`) **[static]**

- `init` enumerates cameras, keeps VID `0xbcdc`: PID `0x0a` becomes CameraA, PID `0x0b` becomes
  CameraB, each a `UVCDualCameraMgr` configured as 1280x720, 10.0 fps.
- Frames and controls go through OpenCV `cv::VideoCapture` (DirectShow under Wine, i.e. qcap → V4L2).
- `enableTextureLight` and `setFPSLevel` are empty on the Lizard.
- `setBrightLevel(level)` maps the level (1-9) through a per-camera table to
  (exposure, gain) and calls `VideoCapture::set(CAP_PROP_EXPOSURE=15, e)` and
  `set(CAP_PROP_GAIN=14, g)`. Exposure is DirectShow log2 seconds; the Wine qcap patch converts it
  to V4L2 `exposure_time_absolute` in 100 µs units (`round(2^e * 10000)`). On the wire this is
  SET_CUR CT `EXPOSURE_TIME_ABSOLUTE` (unit 1, selector 4, u32 LE) then PU `GAIN` (unit 2,
  selector 4, u16 LE). **[usb]** Brightness 1→2→3→4→5→6→5 on CameraA (2026-10-29 22:13:27) sent
  exactly table A's values; level 5 on both cameras at scan start sent 20/30 to each (tables agree).
- The Sensitivity slider produced no USB traffic **[usb]**; it appears to be a host-side parameter.

| Level | A exposure | A gain | B exposure | B gain | V4L2 exposure (100 µs) |
|---|---|---|---|---|---|
| 1 | -11 | 30 | -11 | 30 | 5 |
| 2 | -11 | 65 | -11 | 60 | 5 |
| 3 | -10 | 40 | -10 | 35 | 10 |
| 4 | -10 | 65 | -10 | 50 | 10 |
| 5 | -9 | 30 | -9 | 30 | 20 |
| 6 | -9 | 63 | -9 | 45 | 20 |
| 7 | -8 | 50 | -8 | 45 | 39 |
| 8 | -8 | 63 | -8 | 65 | 39 |
| 9 | -7 | 63 | -7 | 30 | 78 |

Table A is at `JMDeviceCore.dll` 0x18001e4a0 (installed for CameraA in `init`). Table B at
0x18001e590 is assumed to be CameraB's; its install site was not traced.

### SLAM switch and scan (Texture SLAM mode) **[usb]**, 2026-10-29 22:27

Timed against JM Studio's own log (`C:\users\peter\AppData\Roaming\Jimuyida\JMStudio\log\JMStudio_YYYYMMDD.log`,
millisecond timestamps, records UI clicks and mode changes; use it to align captures):

| Time | JM Studio log | USB |
|---|---|---|
| 22:27:07.154 | `CameraScanModeChanged: Geometry → Texture` | 07.307-07.945: steps 1-4 below |
| 22:27:09.047 | `ButtonBox clicked: Scan`, `Start record...` | nothing |
| 22:27:14.147 | `ButtonBox clicked: Scan` (stop), `End record...5 secs` | 14.315/14.347: step 6 |
| 22:27:14.995 | `Switch to Edit mode` | devices closed |

The SLAM-mode switch is what reconfigures the cameras (Texture adds CameraB). Starting and running a
scan sends no control traffic; recording is host-side processing of frames already streaming.

1. CameraA `SET_INTERFACE` VS iface 1 alt 0 (stop preview).
2. CameraA VS PROBE: SET_CUR `01 00 | 01 | 02 | 40 42 0f 00 | 0…` (bmHint=1, format 1 = MJPEG,
   frame 2 = 1280x720, interval 1 000 000 x 100 ns = 10 fps); GET_MIN/GET_MAX/SET_CUR/GET_CUR,
   device answers wDelay 32, dwMaxVideoFrameSize 1 843 200, dwMaxPayloadTransferSize 0x600.
   VS COMMIT with the negotiated block, then `SET_INTERFACE` alt 4.
3. CameraB: identical probe/commit, alt 4.
4. Exposure 20 / gain 30 (brightness 5) to CameraA, then CameraB.
5. Scan click, recording (5 s, 51 frames): **no control traffic at all**.
6. Scan stop: `SET_INTERFACE` alt 0 on both; JM Studio closes both devices on switching to Edit mode.

No XU command, no vendor request and no other device is involved in starting a scan.

### Projector check without JM Studio **[usb]**, 2026-10-29 22:31-22:33

With JM Studio closed, plain `v4l2-ctl --set-fmt-video=width=1280,height=720,pixelformat=MJPG
--set-parm=10 --stream-mmap` (no controls set; the cameras kept exposure 20 / gain 30). The wire
carried only GET_STATUS, VS PROBE/COMMIT (byte-identical to JM Studio's) and SET_INTERFACE.

- CameraA alone: dense static projected line pattern on the object, with hard projector shadows.
  Frame-to-frame difference is flat at ~2.7 grey levels (noise), so the pattern is fixed, not
  phase-stepped.
- CameraB alone: evenly lit image, no projected pattern, only the object's own texture.
- Both together: CameraA shows the pattern, CameraB still does not.

So the structured-light projector needs no host command: it is on while CameraA streams (whether
it is also on when idle was not checked). CameraB is the texture camera and does not see the
pattern; a different spectral filter is the likely reason **[inferred]**. Running the scanner
natively needs only the two UVC streams at 1280x720 MJPEG 10 fps plus exposure/gain, and the
per-device calibration that JM Studio loads by serial (`Load Calib file successed! sn=...`).

### Extension Unit tunnel (HCamera_x64.dll) **[static]**

All XU access is `IKsControl::KsProperty` with KS node 3 (UVC unit 4), 8-byte payloads:

1. SET_CUR selector 10: command `[tag, op, addr_lo, addr_hi, len, 0, 0, 0]`.
2. Then ceil(len/8) transfers on selector 11: GET_CUR to read, SET_CUR to write.

| Export | tag | op | Notes |
|---|---|---|---|
| `hRclReadReg8/16` | 00 | CA | len 2, value big-endian `d[0]<<8 \| d[1]` (Reg8 returns `d[0]`) |
| `hRclWriteReg8/16` | 00 | 8A | len 2, big-endian (Reg8 is value<<8) |
| `hRclReadMem(Buf)` | 00 | C2 | len 1-8 |
| `hRclWriteMem(Buf)` | 00 | 82 | len 1-8 |
| `hRclReadFlash` | 02 | C2 | `[02 C2 a0 a1 lenL lenH a2 00]`: 24-bit address, 16-bit length |
| `hRclWriteFlash` | | | sets bit 0 of mem 0xFEA0 and 0xFEA6, then `02 83 ...`; do not use |

JM Studio only imports `hEnumVideoDevice`, `hFreeVideoDevice` and `hRclReadFlash`. The one use is
the device serial: `hRclReadFlash(dev, 0xFE00, buf, 0x14)`, serial = 15 bytes at `buf+4`, accepted if
it starts with `JM` or `CR`. Expected wire form **[inferred]**: SET_CUR sel 10
`02 C2 00 FE 14 00 00 00`, then three GET_CUR sel 11. A second path reads 10-11 bytes at flash
0x1F100 via `SonixCamera.dll` `SonixCam_SerialFlashRead` (prefix `CRSL`); which path this unit
answers is not yet known.

### Capture tooling

- usbmon: user is in `plugdev`, `/dev/usbmon*` is `root:plugdev 0660` (from `~/tmp/setup-tracing.sh`,
  revert with `--revert`). A passive reader that keeps only control/interrupt URBs for given VID:PIDs
  (iso counted, not stored) avoids ring-buffer drops at 2x isochronous video.
- Toolbox `rea`: `wireshark-cli` (tshark, capinfos), `java-21-openjdk-devel`. Ghidra 12.1.4 in
  `~/Apps/ghidra_12.1.4_PUBLIC`, run headless with `toolbox run -c rea .../support/analyzeHeadless`.
- Another process using the cameras (e.g. `v4l2-ctl` tests) shows up as VS PROBE/COMMIT and
  SET_INTERFACE on the same device; check fd holders before attributing traffic to JM Studio.

### Driving the GUI

`ydotool` moves the pointer (after `mousemove -a -x 0 -y 0`, one relative unit = 2 logical px at
scale 1.5, i.e. 3 X-root px) but its clicks never reached the Wine window. XWayland ignores XTEST
motion, and XTEST button presses at a `ydotool`-placed pointer also produced no effect. Clicks by
hand were the only working route on 2026-10-29.

### Open items

- Capture a JM Studio start to see the serial read path (XU flash 0xFE00 vs Sonix 0x1F100).
- Where the calibration that JM Studio loads by serial comes from (local file vs device flash).
