#!/usr/bin/env bash
# Start Claude Code on the real C128, by hand.
#
# For unattended use install claude-c128.service instead — it does the same
# thing at boot and respawns on a lost link. This script is for a one-off run
# or for testing a fresh client build.
#
# Run it from a normal shell: launched from a sandboxed one the bridge inherits
# a read-only ~/.claude and Claude Code's SessionStart hook then floods the
# screen with EROFS errors.
set -euo pipefail

HOST="${CBM_ULTIMATE_HOST:-192.168.1.237}"
DIR="${1:-$HOME}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "building client and boot disk ..."
make -C "$ROOT/client" >/dev/null
python3 "$ROOT/tools/mkbootdisk.py" "$ROOT/client/build/claude.prg" \
        -o "$ROOT/client/build/claude-boot.d64" >/dev/null

# Push the fresh disk to the Ultimate's own storage so the boot survives a
# power cycle. The REST file-upload endpoint is unimplemented in firmware 3.11,
# so this goes over FTP.
echo "uploading the boot disk to $HOST ..."
python3 - "$HOST" "$ROOT/client/build/claude-boot.d64" <<'PY'
import ftplib, sys
host, path = sys.argv[1], sys.argv[2]
f = ftplib.FTP(host, timeout=30); f.login(); f.cwd("/Usb0")
with open(path, "rb") as fh:
    f.storbinary("STOR claude-boot.d64", fh)
f.quit()
print("  uploaded to /Usb0/claude-boot.d64")
PY

# Mount and reset unless a client is already running.
python3 "$ROOT/server/bootstrap.py" --host "$HOST" --force

echo "dialling $HOST:3000 ..."
tmux kill-session -t c128 2>/dev/null || true
tmux new-session -d -s c128 \
  "cd '$ROOT' && python3 server/bridge.py --connect $HOST:3000 \
   --command claude --cwd '$DIR' -v 2>&1 | tee hwbridge.log"

sleep 25
echo
echo "80-column screen:"
python3 "$ROOT/tools/vdcpeek.py" || true
echo
echo "running in tmux session 'c128'.  attach: tmux attach -t c128"
echo "stop:  tmux kill-session -t c128"
echo "on the C128, HELP forces a full repaint and re-arms the modem."
