#!/usr/bin/env python3
"""Capture frames from a CR-Scan Lizard natively (V4L2, no Wine, no JM Studio).

Replicates what JM Studio sends on the wire (see NOTES.md):
  - CameraA (bcdc:000a) streams in both SLAM modes and lights the structured-light
    projector while it streams; CameraB (bcdc:000b) is added in texture mode.
  - Both run MJPEG 1280x720 at 10 fps.
  - Brightness level 1-9 maps to per-camera (exposure, gain) tables; exposure is
    V4L2 exposure_time_absolute in 100 us units, auto_exposure is set to manual.
  - The serial is read from CameraA's flash at 0xFE00 through the UVC extension
    unit (unit 4: command on selector 10, data on selector 11). This is the same
    read-only request JM Studio sends at every start; --no-serial skips it.

Output: OUT/A/NNNNNN.jpg, OUT/B/NNNNNN.jpg, OUT/frames.csv (one row per frame,
with the driver's CLOCK_MONOTONIC buffer timestamp for pairing A/B), OUT/meta.json.

Close JM Studio (or switch it to Edit mode) first; the cameras allow one streamer.

Usage: lizard_capture.py OUT [--mode geometry|texture] [--brightness 1-9]
                             [--frames N | --seconds S] [--no-serial]
"""
import argparse
import csv
import ctypes
import errno
import fcntl
import glob
import json
import mmap
import os
import select
import struct
import sys
import time
from pathlib import Path

VID = "bcdc"
PIDS = {"A": "000a", "B": "000b"}
WIDTH, HEIGHT, FPS = 1280, 720, 10

# Brightness level -> (exposure in 100 us units, gain). JM Studio stores exposure as
# DirectShow log2 seconds (-11..-7); Wine's qcap converts that to round(2^e * 1e4).
EXPOSURE = {-11: 5, -10: 10, -9: 20, -8: 39, -7: 78}
TABLE = {  # level: (exposure log2 s, gain A, gain B), from JMDeviceCore.dll 0x18001e4a0 / 0x18001e590
    1: (-11, 30, 30), 2: (-11, 65, 60), 3: (-10, 40, 35), 4: (-10, 65, 50), 5: (-9, 30, 30),
    6: (-9, 63, 45), 7: (-8, 50, 45), 8: (-8, 63, 65), 9: (-7, 63, 30),
}


def _ioc(direction, nr, size, kind="V"):
    return (direction << 30) | (size << 16) | (ord(kind) << 8) | nr


_IOW, _IOR, _IOWR = 1, 2, 3
VIDIOC_QUERYCAP = _ioc(_IOR, 0, 104)
VIDIOC_S_FMT = _ioc(_IOWR, 5, 208)
VIDIOC_REQBUFS = _ioc(_IOWR, 8, 20)
VIDIOC_QUERYBUF = _ioc(_IOWR, 9, 88)
VIDIOC_QBUF = _ioc(_IOWR, 15, 88)
VIDIOC_DQBUF = _ioc(_IOWR, 17, 88)
VIDIOC_STREAMON = _ioc(_IOW, 18, 4)
VIDIOC_STREAMOFF = _ioc(_IOW, 19, 4)
VIDIOC_S_PARM = _ioc(_IOWR, 22, 204)
VIDIOC_G_CTRL = _ioc(_IOWR, 27, 8)
VIDIOC_S_CTRL = _ioc(_IOWR, 28, 8)
UVCIOC_CTRL_QUERY = _ioc(_IOWR, 0x21, 16, "u")

BUF_TYPE_CAPTURE, MEMORY_MMAP = 1, 1
CAP_VIDEO_CAPTURE = 0x1
BUF_FLAG_ERROR = 0x40
PIX_MJPG = struct.unpack("<I", b"MJPG")[0]
CID_GAIN, CID_EXPOSURE_AUTO, CID_EXPOSURE_ABSOLUTE = 0x00980913, 0x009A0901, 0x009A0902
EXPOSURE_MANUAL = 1
UVC_SET_CUR, UVC_GET_CUR = 0x01, 0x81
XU_UNIT, XU_SEL_CMD, XU_SEL_DATA = 4, 10, 11
NBUFS = 4

# struct v4l2_buffer on 64-bit Linux (88 bytes)
BUF = struct.Struct("<IIIII4xqq16sIIQIII4x")


def find_capture_node(pid):
    """Return the /dev/videoN capture node of the USB device VID:pid, or None."""
    for node in sorted(glob.glob("/sys/class/video4linux/video*")):
        usb = Path(node, "device").resolve().parent
        try:
            if (usb / "idVendor").read_text().strip() != VID or (usb / "idProduct").read_text().strip() != pid:
                continue
        except OSError:
            continue
        dev = "/dev/" + os.path.basename(node)
        fd = os.open(dev, os.O_RDWR | os.O_NONBLOCK)
        try:
            cap = bytearray(104)
            fcntl.ioctl(fd, VIDIOC_QUERYCAP, cap)
            if struct.unpack_from("<I", cap, 88)[0] & CAP_VIDEO_CAPTURE:
                return dev
        finally:
            os.close(fd)
    return None


def set_ctrl(fd, cid, value):
    fcntl.ioctl(fd, VIDIOC_S_CTRL, struct.pack("<Ii", cid, value))
    return struct.unpack("<Ii", fcntl.ioctl(fd, VIDIOC_G_CTRL, struct.pack("<Ii", cid, 0)))[1]


def xu_query(fd, query, selector, payload):
    buf = ctypes.create_string_buffer(bytes(payload), len(payload))
    arg = struct.pack("<BBBxH2xQ", XU_UNIT, selector, query, len(payload), ctypes.addressof(buf))
    fcntl.ioctl(fd, UVCIOC_CTRL_QUERY, arg)
    return buf.raw


def read_serial(fd):
    """hRclReadFlash(dev, 0xFE00, buf, 0x14): serial is NUL-terminated at buf+4."""
    xu_query(fd, UVC_SET_CUR, XU_SEL_CMD, bytes([0x02, 0xC2, 0x00, 0xFE, 0x14, 0, 0, 0]))
    raw = b"".join(xu_query(fd, UVC_GET_CUR, XU_SEL_DATA, bytes(8)) for _ in range(3))
    return raw[4:20].split(b"\0", 1)[0].decode("ascii", "replace"), raw[:0x14].hex()


class Camera:
    def __init__(self, name, dev, exposure, gain):
        self.name, self.dev = name, dev
        self.fd = os.open(dev, os.O_RDWR | os.O_NONBLOCK)
        self.maps = []
        self.streaming = False

        fmt = bytearray(208)
        struct.pack_into("<I", fmt, 0, BUF_TYPE_CAPTURE)
        struct.pack_into("<IIII", fmt, 8, WIDTH, HEIGHT, PIX_MJPG, 0)
        fcntl.ioctl(self.fd, VIDIOC_S_FMT, fmt)
        w, h, pix = struct.unpack_from("<III", fmt, 8)
        if (w, h, pix) != (WIDTH, HEIGHT, PIX_MJPG):
            raise SystemExit(f"{dev}: driver chose {w}x{h} {pix:#x}, not {WIDTH}x{HEIGHT} MJPG")

        parm = bytearray(204)
        struct.pack_into("<I", parm, 0, BUF_TYPE_CAPTURE)
        struct.pack_into("<II", parm, 12, 1, FPS)  # timeperframe = 1/FPS
        fcntl.ioctl(self.fd, VIDIOC_S_PARM, parm)

        self.controls = {
            "auto_exposure": set_ctrl(self.fd, CID_EXPOSURE_AUTO, EXPOSURE_MANUAL),
            "exposure_time_absolute": set_ctrl(self.fd, CID_EXPOSURE_ABSOLUTE, exposure),
            "gain": set_ctrl(self.fd, CID_GAIN, gain),
        }

        req = bytearray(struct.pack("<III8x", NBUFS, BUF_TYPE_CAPTURE, MEMORY_MMAP))
        fcntl.ioctl(self.fd, VIDIOC_REQBUFS, req)
        for i in range(struct.unpack_from("<I", req, 0)[0]):
            b = bytearray(BUF.pack(i, BUF_TYPE_CAPTURE, 0, 0, 0, 0, 0, b"", 0, MEMORY_MMAP, 0, 0, 0, 0))
            fcntl.ioctl(self.fd, VIDIOC_QUERYBUF, b)
            f = BUF.unpack(b)
            self.maps.append(mmap.mmap(self.fd, f[11], mmap.MAP_SHARED, mmap.PROT_READ, offset=f[10]))
            fcntl.ioctl(self.fd, VIDIOC_QBUF, b)

    def start(self):
        fcntl.ioctl(self.fd, VIDIOC_STREAMON, struct.pack("<I", BUF_TYPE_CAPTURE))
        self.streaming = True

    def dequeue(self):
        """Return (sequence, monotonic seconds, jpeg bytes, complete, driver_error), or None.

        complete is False when the frame lacks the JPEG start or end marker (the first frame
        after STREAMON is routinely cut short). driver_error is uvcvideo's V4L2_BUF_FLAG_ERROR:
        these cameras raise it on most frames, but ~95% of flagged frames decode fully, so it
        is recorded rather than used to drop frames (v4l2-ctl and JM Studio ignore it too)."""
        b = bytearray(BUF.pack(0, BUF_TYPE_CAPTURE, 0, 0, 0, 0, 0, b"", 0, MEMORY_MMAP, 0, 0, 0, 0))
        try:
            fcntl.ioctl(self.fd, VIDIOC_DQBUF, b)
        except OSError as e:
            if e.errno == errno.EAGAIN:
                return None
            raise
        f = BUF.unpack(b)
        frame = self.maps[f[0]][: f[2]]
        fcntl.ioctl(self.fd, VIDIOC_QBUF, b)
        complete = frame.startswith(b"\xff\xd8") and frame.endswith(b"\xff\xd9")
        return f[8], f[5] + f[6] / 1e6, frame, complete, bool(f[3] & BUF_FLAG_ERROR)

    def close(self):
        if self.streaming:
            fcntl.ioctl(self.fd, VIDIOC_STREAMOFF, struct.pack("<I", BUF_TYPE_CAPTURE))
        for m in self.maps:
            m.close()
        os.close(self.fd)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out", type=Path, help="output directory (created)")
    ap.add_argument("--mode", choices=("geometry", "texture"), default="texture",
                    help="geometry: CameraA only; texture: CameraA + CameraB (default)")
    ap.add_argument("--brightness", type=int, choices=range(1, 10), default=5, metavar="1-9")
    stop = ap.add_mutually_exclusive_group()
    stop.add_argument("--frames", type=int, help="frames per camera (default 50)")
    stop.add_argument("--seconds", type=float, help="capture duration instead of a frame count")
    ap.add_argument("--no-serial", action="store_true", help="skip the extension-unit serial read")
    args = ap.parse_args()
    if args.frames is None and args.seconds is None:
        args.frames = 50

    names = ["A"] if args.mode == "geometry" else ["A", "B"]
    devs = {n: find_capture_node(PIDS[n]) for n in names}
    missing = [n for n, d in devs.items() if d is None]
    if missing:
        raise SystemExit(f"Camera{'/'.join(missing)} ({VID}:{'/'.join(PIDS[n] for n in missing)}) not found")

    log2_exposure, gain_a, gain_b = TABLE[args.brightness]
    gains = {"A": gain_a, "B": gain_b}
    args.out.mkdir(parents=True, exist_ok=True)

    cams = {}
    try:
        for n in names:
            try:
                cams[n] = Camera(n, devs[n], EXPOSURE[log2_exposure], gains[n])
            except OSError as e:
                if e.errno == errno.EBUSY:
                    raise SystemExit(f"{devs[n]} is busy; close JM Studio or switch it to Edit mode")
                raise
            (args.out / n).mkdir(exist_ok=True)

        meta = {
            "mode": args.mode, "brightness": args.brightness, "width": WIDTH, "height": HEIGHT, "fps": FPS,
            "cameras": {n: {"device": c.dev, "controls": c.controls} for n, c in cams.items()},
            "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        if not args.no_serial:
            meta["serial"], meta["flash_0xfe00"] = read_serial(cams["A"].fd)
            print(f"serial {meta['serial']}", file=sys.stderr)

        for c in cams.values():
            c.start()
        counts = dict.fromkeys(cams, 0)
        dropped = dict.fromkeys(cams, 0)
        deadline = time.monotonic() + args.seconds if args.seconds else None
        with open(args.out / "frames.csv", "w", newline="") as fh:
            rows = csv.writer(fh)
            rows.writerow(["camera", "index", "sequence", "timestamp_monotonic", "bytes", "driver_error", "file"])
            by_fd = {c.fd: c for c in cams.values()}
            while True:
                if deadline is not None and time.monotonic() >= deadline:
                    break
                if args.frames is not None and all(v >= args.frames for v in counts.values()):
                    break
                ready, _, _ = select.select(list(by_fd), [], [], 2.0)
                if not ready:
                    raise SystemExit("no frame for 2 s; is another program streaming the cameras?")
                for fd in ready:
                    c = by_fd[fd]
                    got = c.dequeue()
                    if got is None or (args.frames is not None and counts[c.name] >= args.frames):
                        continue
                    seq, ts, jpeg, complete, driver_error = got
                    if not complete:
                        dropped[c.name] += 1
                        continue
                    name = f"{c.name}/{counts[c.name]:06d}.jpg"
                    (args.out / name).write_bytes(jpeg)
                    rows.writerow([c.name, counts[c.name], seq, f"{ts:.6f}", len(jpeg), int(driver_error), name])
                    counts[c.name] += 1
        meta["frames"] = counts
        meta["dropped_incomplete"] = dropped
        (args.out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
        print(f"wrote {counts} to {args.out}, dropped incomplete {dropped}", file=sys.stderr)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
    finally:
        for c in cams.values():
            c.close()


if __name__ == "__main__":
    main()
