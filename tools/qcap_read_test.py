#!/usr/bin/env python3
"""Repeat Wine qcap's camera read path through libv4l2 to catch stream-start failures.

Wine's qcap (dlls/qcap/v4l.c) opens the node with v4l2_open(O_RDWR | O_NONBLOCK), sets
BGR24 at the capture size with VIDIOC_S_FMT (libv4l2 then streams MJPEG and decodes it), and
calls v4l2_read() in a loop, retrying only on EAGAIN. Any other error ends qcap's stream
thread for good, which JM Studio shows as a camera that starts and then delivers nothing.

Run it inside the Flatpak so it uses the same libv4l2 as Wine there:
  flatpak run --command=python3 --env=LIBV4L2_LOG_FILENAME=/tmp/libv4l2.log \
      io.github.poita66.jmstudio qcap_read_test.py /dev/video3 [starts] [frames] [idle seconds]
"""
import ctypes, ctypes.util, errno, fcntl, os, struct, sys, time

V4L2_BUF_TYPE_VIDEO_CAPTURE = 1
V4L2_PIX_FMT_BGR24 = int.from_bytes(b"BGR3", "little")
VIDIOC_S_FMT = (3 << 30) | (208 << 16) | (ord("V") << 8) | 5

lib = ctypes.CDLL("libv4l2.so.0", use_errno=True)
lib.v4l2_open.argtypes = [ctypes.c_char_p, ctypes.c_int]
lib.v4l2_ioctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]
lib.v4l2_read.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t]
lib.v4l2_read.restype = ctypes.c_ssize_t
lib.v4l2_close.argtypes = [ctypes.c_int]


def one_start(path, frames, width=1280, height=720, timeout=5.0):
    """Return (outcome, errno name, frames read, seconds from open to first frame)."""
    t0 = time.monotonic()
    first = None
    fd = lib.v4l2_open(path.encode(), os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
    if fd < 0:
        return "open", errno.errorcode.get(ctypes.get_errno(), ctypes.get_errno()), 0, None
    try:
        fmt = ctypes.create_string_buffer(208)
        # struct v4l2_format: type, then the fmt union at offset 8 (8-byte aligned on 64-bit).
        struct.pack_into("<I", fmt, 0, V4L2_BUF_TYPE_VIDEO_CAPTURE)
        struct.pack_into("<III", fmt, 8, width, height, V4L2_PIX_FMT_BGR24)
        if lib.v4l2_ioctl(fd, VIDIOC_S_FMT, fmt) < 0:
            return "s_fmt", errno.errorcode.get(ctypes.get_errno(), ctypes.get_errno()), 0, None
        size = width * height * 3
        buf = ctypes.create_string_buffer(size)
        got, deadline = 0, time.monotonic() + timeout
        while got < frames:
            if lib.v4l2_read(fd, buf, size) < 0:
                err = ctypes.get_errno()
                if err != errno.EAGAIN:
                    return "read", errno.errorcode.get(err, err), got, first
                if time.monotonic() > deadline:
                    return "timeout", "", got, first
                time.sleep(0.002)
                continue
            if first is None:
                first = time.monotonic() - t0
            got += 1
        return "ok", "", got, first
    finally:
        lib.v4l2_close(fd)


def main():
    path = sys.argv[1]
    starts = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    frames = int(sys.argv[3]) if len(sys.argv) > 3 else 15
    idle = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
    results, firsts = {}, []
    for i in range(starts):
        if i and idle:
            time.sleep(idle)
        outcome = one_start(path, frames)
        results[outcome[:2]] = results.get(outcome[:2], 0) + 1
        if outcome[3] is not None:
            firsts.append(outcome[3])
        if outcome[0] != "ok" or idle:
            first = f"{outcome[3] * 1000:.0f} ms" if outcome[3] is not None else "none"
            print(f"start {i}: {outcome[0]} {outcome[1]} frames={outcome[2]} first frame {first}",
                  flush=True)
    print({f"{k[0]} {k[1]}".strip(): v for k, v in results.items()})
    if firsts:
        firsts.sort()
        print(f"open to first frame: min {firsts[0] * 1000:.0f} ms, "
              f"median {firsts[len(firsts) // 2] * 1000:.0f} ms, max {firsts[-1] * 1000:.0f} ms")


if __name__ == "__main__":
    main()
