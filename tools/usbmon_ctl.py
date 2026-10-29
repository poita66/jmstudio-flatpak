#!/usr/bin/env python3
"""Passive usbmon reader: logs control/interrupt/bulk URBs for selected VID:PIDs as JSONL.

Iso URBs are counted per device but not stored. Uses MON_IOCX_GETX (64-byte header).
Usage: usbmon_ctl.py BUS OUT.jsonl SECONDS VID:PID [VID:PID ...]
"""
import ctypes, fcntl, json, os, struct, sys, time, glob

MON_IOC_MAGIC = 0x92
def _IOC(d, t, nr, size): return (d << 30) | (size << 16) | (t << 8) | nr
MON_IOCG_STATS = _IOC(2, MON_IOC_MAGIC, 3, 8)
MON_IOCT_RING_SIZE = _IOC(0, MON_IOC_MAGIC, 4, 0)
MON_IOCX_GETX = _IOC(1, MON_IOC_MAGIC, 10, 24)
HDR = struct.Struct("<QBBBBHccqiiII8siiII")  # 64 bytes
XFER = {0: "iso", 1: "intr", 2: "ctrl", 3: "bulk"}
UVC_REQ = {0x01: "SET_CUR", 0x81: "GET_CUR", 0x82: "GET_MIN", 0x83: "GET_MAX",
           0x84: "GET_RES", 0x85: "GET_LEN", 0x86: "GET_INFO", 0x87: "GET_DEF"}

def devnums(bus, ids):
    out = {}
    for p in glob.glob("/sys/bus/usb/devices/*"):
        try:
            vp = open(p + "/idVendor").read().strip() + ":" + open(p + "/idProduct").read().strip()
            if vp in ids and int(open(p + "/busnum").read()) == bus:
                out[int(open(p + "/devnum").read())] = vp
        except OSError:
            pass
    return out

def main():
    bus, path, secs, ids = int(sys.argv[1]), sys.argv[2], float(sys.argv[3]), sys.argv[4:]
    devs = devnums(bus, ids)
    fd = os.open(f"/dev/usbmon{bus}", os.O_RDONLY)
    try:
        fcntl.ioctl(fd, MON_IOCT_RING_SIZE, 1200 * 1024)
    except OSError:
        pass
    hdr = ctypes.create_string_buffer(64)
    data = ctypes.create_string_buffer(65536)
    get = struct.pack("<QQQ", ctypes.addressof(hdr), ctypes.addressof(data), len(data))
    getbuf = ctypes.create_string_buffer(get, 24)
    iso = {}
    stats0 = struct.unpack("<II", fcntl.ioctl(fd, MON_IOCG_STATS, b"\0" * 8))
    end = time.time() + secs
    with open(path, "w") as f:
        f.write(json.dumps({"meta": "start", "t": time.time(), "devs": devs, "stats": stats0}) + "\n")
        while time.time() < end:
            fcntl.ioctl(fd, MON_IOCX_GETX, getbuf)  # blocks until an event
            (uid, typ, xt, ep, dev, busn, fs, fd_, sec, usec, status, len_urb, len_cap,
             setup, interval, start_frame, xflags, ndesc) = HDR.unpack(hdr.raw[:64])
            if dev not in devs:
                continue
            if xt == 0:
                iso[dev] = iso.get(dev, 0) + 1
                continue
            rec = {"t": sec + usec / 1e6, "id": uid, "ev": chr(typ), "dev": dev, "vp": devs[dev],
                   "xfer": XFER[xt], "ep": f"{ep:#04x}", "status": status, "len": len_urb}
            if fs == b"\0":  # setup packet present (submission of a control URB)
                bm, breq, wv, wi, wl = struct.unpack("<BBHHH", setup)
                rec.update(bmRequestType=f"{bm:#04x}", bRequest=f"{breq:#04x}",
                           wValue=f"{wv:#06x}", wIndex=f"{wi:#06x}", wLength=wl)
                if bm & 0x60 == 0x20:  # class request
                    rec["uvc"] = UVC_REQ.get(breq, "?")
                    rec["unit"], rec["iface"], rec["selector"] = wi >> 8, wi & 0xff, wv >> 8
            if len_cap and fd_ == b"\0":
                rec["data"] = data.raw[:min(len_cap, len(data))].hex()
            f.write(json.dumps(rec) + "\n")
            f.flush()
        stats1 = struct.unpack("<II", fcntl.ioctl(fd, MON_IOCG_STATS, b"\0" * 8))
        f.write(json.dumps({"meta": "end", "t": time.time(), "iso_urbs": iso, "stats": stats1}) + "\n")

if __name__ == "__main__":
    main()
