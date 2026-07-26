#!/usr/bin/env bash
# Start Claude Code on the real C128.
#
# Order matters: the Ultimate's modem layer only comes up once a program
# configures the ACIA, so the client is loaded and running before the bridge
# dials in. Run this from a normal shell — launched from a sandboxed one the
# bridge inherits a read-only ~/.claude and Claude Code's SessionStart hook
# then floods the screen with errors.
set -euo pipefail

HOST="${CBM_ULTIMATE_HOST:-192.168.1.237}"
DIR="${1:-$HOME}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CBM="$HOME/.claude/skills/commodore-basic/bin/cbm"

echo "building client ..."
make -C "$ROOT/client" disk >/dev/null

echo "loading the client on the C128 ..."
"$CBM" --target c128 deploy "$ROOT/client/build/claude.prg" \
       --name claude --reset --timeout 25 >/dev/null
sleep 8

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
