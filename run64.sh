#!/usr/bin/env bash
#
# Bring the C64 client up on real hardware.
#
# On a physical C64 this is overkill - LOAD and RUN the .prg however you like,
# then dial. It exists for the common case of a C128, where getting into C64
# mode is the whole problem:
#
#   * The Ultimate's run_prg resets the machine, and a C128 resets into C128
#     mode. It then accepts a C64 .prg (which loads at $0801, not where BASIC
#     7.0 keeps a program), reports no error, and leaves you at a BASIC 7.0
#     prompt. Verified on hardware - it looks like it worked and did nothing.
#   * So the mode switch has to go through the keyboard first: GO64, confirm,
#     LOAD, RUN. That is what tools/go64.py does.
#
# The claude-c128 service must not be running: its bootstrap step re-mounts the
# C128 boot disk and resets the machine whenever it cannot see a client, which
# pulls the machine straight back out of C64 mode. This stops it and puts it
# back on exit.
set -euo pipefail
HOST="${CBM_ULTIMATE_HOST:-192.168.1.237}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RESTART_SERVICE=0
if systemctl --user is-active --quiet claude-c128 2>/dev/null; then
    RESTART_SERVICE=1
    echo "stopping the claude-c128 service for the duration ..."
    systemctl --user stop claude-c128
fi
restore() {
    if [ "$RESTART_SERVICE" = "1" ]; then
        echo
        echo "restarting the claude-c128 service (back to the C128 client) ..."
        systemctl --user start claude-c128
    fi
}
trap restore EXIT

echo "building the C64 client and disk ..."
make -C "$ROOT/client" disk64 >/dev/null

echo "uploading to $HOST ..."
python3 - "$HOST" "$ROOT/client/build/claude64.d64" <<'PY'
import ftplib, sys
host, path = sys.argv[1], sys.argv[2]
f = ftplib.FTP(host, timeout=30); f.login(); f.cwd("/Usb0")
with open(path, "rb") as fh:
    f.storbinary("STOR claude64.d64", fh)
f.quit()
print("  uploaded to /Usb0/claude64.d64")
PY

python3 "$ROOT/tools/go64.py" --host "$HOST"

echo "dialling $HOST:3000 ..."
python3 "$ROOT/server/bridge.py" --machine c64 --connect "$HOST:3000" "$@"
