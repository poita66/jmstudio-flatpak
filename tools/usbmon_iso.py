#!/usr/bin/env python3
"""usbmon iso reader: per completed iso URB, log packet statuses and UVC payload header flags.

Usage: usbmon_iso.py BUS OUT.jsonl SECONDS VID:PID [VID:PID ...]
"""
import ctypes, fcntl, json, os, struct, sys, time, collections
sys.path.insert(0, os.path.dirname(__file__))
from usbmon_ctl import MON_IOCG_STATS, MON_IOCT_RING_SIZE, MON_IOCX_GETX, HDR, devnums

ISO = struct.Struct("<iIII")

def main():
    bus, path, secs, ids = int(sys.argv[1]), sys.argv[2], float(sys.argv[3]), sys.argv[4:]
    devs = devnums(bus, ids)
    fd = os.open(f"/dev/usbmon{bus}", os.O_RDONLY)
    fcntl.ioctl(fd, MON_IOCT_RING_SIZE, 64 * 1024 * 1024 - 4096)
    hdr = ctypes.create_string_buffer(64)
    data = ctypes.create_string_buffer(1 << 20)
    getbuf = ctypes.create_string_buffer(
        struct.pack("<QQQ", ctypes.addressof(hdr), ctypes.addressof(data), len(data)), 24)
    stats0 = struct.unpack("<II", fcntl.ioctl(fd, MON_IOCG_STATS, b"\0" * 8))
    end = time.time() + secs
    with open(path, "w") as f:
        f.write(json.dumps({"meta": "start", "devs": devs, "stats": stats0}) + "\n")
        while time.time() < end:
            fcntl.ioctl(fd, MON_IOCX_GETX, getbuf)
            (uid, typ, xt, ep, dev, busn, fs, fd_, sec, usec, status, len_urb, len_cap,
             setup, interval, start_frame, xflags, ndesc) = HDR.unpack(hdr.raw[:64])
            if dev not in devs or xt != 0 or typ != ord("C"):
                continue
            err_count, numdesc = struct.unpack("<ii", setup)
            raw = data.raw[:len_cap]
            descs = [ISO.unpack_from(raw, i * 16) for i in range(min(ndesc, len_cap // 16))]
            base = ndesc * 16
            st = collections.Counter()
            pk = []
            for s, off, ln, _ in descs:
                st[s] += 1
                if s == 0 and ln >= 2 and base + off + 2 <= len(raw):
                    hl, info = raw[base + off], raw[base + off + 1]
                    pk.append([ln, info])
                else:
                    pk.append([ln, s])
            f.write(json.dumps({"t": sec + usec / 1e6, "dev": dev, "status": status,
                                "err": err_count, "n": numdesc, "st": dict(st),
                                "sf": start_frame, "len": len_urb, "cap": len_cap,
                                "pk": pk}) + "\n")
        stats1 = struct.unpack("<II", fcntl.ioctl(fd, MON_IOCG_STATS, b"\0" * 8))
        f.write(json.dumps({"meta": "end", "stats": stats1}) + "\n")

if __name__ == "__main__":
    main()
