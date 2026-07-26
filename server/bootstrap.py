#!/usr/bin/env python3
"""Get the C128 into a state where the bridge can dial it.

The Ultimate II+ has no "mount this image at startup" setting — every config
category was checked — so a cold power-on leaves drive A empty and nothing
autoboots. The Linux side is the always-on half, so it does the bring-up:
mount the boot disk, reset, and wait for the client to come up.

Idempotent and safe to run repeatedly, which is what makes it usable as a
systemd ExecStartPre: if the client is already running it changes nothing and
returns immediately, so a bridge restart never resets a machine someone is
using.

Liveness is decided by reading the 40-column screen at $0400, not the ACIA.
Reading $DE00-$DE03 over DMA pops bytes off the 6551's receive register and
would corrupt a live session; ordinary RAM is safe to read.
"""
import argparse
import sys
import time
import urllib.error
import urllib.request

HOST = "192.168.1.237"
VIC_SCREEN = 0x0400
BOOT_IMAGE = "/Usb0/claude-boot.d64"

# The Ultimate must expose the 6551 at $DE00 on NMI or the client has nothing to
# talk to. This setting has been observed reverting to "Off" across a device
# reboot even after save_to_flash, and the symptom is opaque — the modem
# listener answers with "Modem Software is currently not running..." — so it is
# re-asserted here and saved on every cold bring-up.
ACIA_CATEGORY = "Modem%20Settings"
ACIA_ITEM = "ACIA%20(6551)%20Mode"
ACIA_VALUE = "DE00%2FNMI"

# The client prints its name on the 40-column screen at startup, and the
# companion panel keeps the word there afterwards, so this marker is present
# for the whole life of a session either way. In screen codes, c=$03 l=$0C
# a=$01 u=$15 d=$04 e=$05.
MARKER = bytes((0x03, 0x0C, 0x01, 0x15, 0x04, 0x05))    # "claude"


def req(host, method, path, data=None, timeout=25):
    r = urllib.request.Request(f"http://{host}{path}", data=data, method=method)
    if data is not None:
        r.add_header("Content-Type", "application/octet-stream")
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.status, resp.read()


def client_running(host):
    """True when the client's name is on the 40-column screen."""
    try:
        _, mem = req(host, "GET",
                     f"/v1/machine:readmem?address={VIC_SCREEN:04X}&length=440")
    except (urllib.error.URLError, OSError):
        return False
    return MARKER in mem


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--image", default=BOOT_IMAGE,
                    help="boot d64 on the Ultimate's own storage")
    ap.add_argument("--drive", default="a")
    ap.add_argument("--wait", type=float, default=40.0,
                    help="seconds to wait for the client to come up")
    ap.add_argument("--force", action="store_true",
                    help="mount and reset even if a client is already running")
    args = ap.parse_args()

    host = args.host

    if not args.force and client_running(host):
        print("[bootstrap] client already running, leaving the machine alone")
        return 0

    try:
        _, cur = req(host, "GET", f"/v1/configs/{ACIA_CATEGORY}/{ACIA_ITEM}")
        if b"DE00/NMI" not in cur:
            print("[bootstrap] ACIA mode is not DE00/NMI, setting it")
            req(host, "PUT",
                f"/v1/configs/{ACIA_CATEGORY}/{ACIA_ITEM}?value={ACIA_VALUE}")
            req(host, "PUT", "/v1/configs:save_to_flash")
        print(f"[bootstrap] mounting {args.image} on drive {args.drive}")
        req(host, "PUT", f"/v1/drives/{args.drive}:mount"
                         f"?image={args.image}&type=d64&mode=readonly")
        print("[bootstrap] resetting; the boot sector will start the client")
        req(host, "PUT", "/v1/machine:reset")
    except (urllib.error.URLError, OSError) as exc:
        print(f"[bootstrap] cannot reach the Ultimate at {host}: {exc}",
              file=sys.stderr)
        return 1

    deadline = time.time() + args.wait
    while time.time() < deadline:
        if client_running(host):
            print("[bootstrap] client is up")
            return 0
        time.sleep(2)

    print(f"[bootstrap] client did not appear within {args.wait:g}s "
          f"(is the C128 powered on?)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
