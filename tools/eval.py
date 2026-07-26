#!/usr/bin/env python3
"""Run every check this project has and report one verdict.

Layered on purpose, cheapest first, so a failure is localised:

  unit          the test suite - glyph table against the character ROM, the
                frame differ, protocol round-trips, character coverage
  coverage      every must-cover Unicode block renders without a question mark
  render        a captured Claude Code session survives the whole pipeline
  emulator      the real compiled 6502 client, in VICE, end to end
  hardware      the live C128, if it is reachable

Anything that needs the physical machine is skipped rather than failed when the
machine is not there, and says so — a skip must never read as a pass.

  python3 tools/eval.py             # everything available
  python3 tools/eval.py --quick     # skip the emulator and hardware
  python3 tools/eval.py --json      # machine-readable
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
HOST = os.environ.get("CBM_ULTIMATE_HOST", "192.168.1.237")

PASS, FAIL, SKIP = "pass", "FAIL", "skip"


def run(cmd, timeout=600, cwd=ROOT):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"


def check_unit():
    rc, out = run([sys.executable, "server/test_bridge.py"], timeout=300)
    last = [l for l in out.splitlines() if "passed" in l]
    return (PASS if rc == 0 else FAIL), (last[-1].strip() if last else out[-200:])


def check_coverage():
    rc, out = run([sys.executable, "tools/charaudit.py", "--strict"], timeout=300)
    if rc == 0:
        blocks = sum(1 for l in out.splitlines() if "  yes" in l)
        return PASS, f"{blocks} must-cover blocks complete"
    gaps = [l.strip() for l in out.splitlines() if "->" in l and ":" in l]
    return FAIL, "; ".join(gaps[:3]) or out[-200:]


def check_render():
    """A real captured session must survive ANSI -> PETSCII -> wire -> screen."""
    cap = os.path.join(ROOT, "docs", "claude_clean.raw")
    if not os.path.exists(cap):
        return SKIP, "no docs/claude_clean.raw fixture"
    rc, out = run([sys.executable, "tools/charaudit.py", "--capture", cap,
                   "--strict"], timeout=120)
    first = out.splitlines()[0] if out else ""
    return (PASS if rc == 0 else FAIL), first.strip()


def check_emulator():
    if not os.path.exists(os.path.join(ROOT, "client", "build", "claude.prg")):
        return SKIP, "client not built (make -C client)"
    disk = os.path.join(ROOT, "client", "build", "claude-boot.d64")
    cmd = [sys.executable, "tools/emutest.py", "--command", "bash --norc -i",
           "--settle", "20"]
    if os.path.exists(disk):
        cmd += ["--bootdisk", disk]
    rc, out = run(cmd, timeout=420)
    if rc != 0:
        return FAIL, out.strip().splitlines()[-1] if out.strip() else "no output"

    # The screen has to show the shell prompt, and nothing may have been lost.
    got_prompt = "bash-" in out
    drops = next((l for l in out.splitlines() if "_rxDropped" in l), "")
    clean = drops.split()[-1] == "0" if drops.split() else False
    if got_prompt and clean:
        return PASS, "client rendered the shell prompt, 0 bytes dropped"
    return FAIL, f"prompt={got_prompt} {drops.strip()}"


def hardware_reachable():
    try:
        urllib.request.urlopen(f"http://{HOST}/v1/version", timeout=5).read()
        return True
    except OSError:
        return False


def check_hardware():
    if not hardware_reachable():
        return SKIP, f"Ultimate at {HOST} not reachable"
    sys.path.insert(0, os.path.join(ROOT, "server"))
    sys.path.insert(0, HERE)
    try:
        from importlib.machinery import SourceFileLoader
        vp = SourceFileLoader("vp", os.path.join(HERE, "vdcpeek.py")).load_module()
        syms = vp.syms()
    except Exception as exc:                       # noqa: BLE001
        return SKIP, f"cannot read client symbols: {exc}"

    try:
        def word(n):
            b = vp.peek(syms[n], 2)
            return b[0] | b[1] << 8

        rx = word("_rxCount")
        dropped = vp.peek(syms["_rxDropped"], 1)[0]
        overruns = vp.peek(syms["_rxOverruns"], 1)[0]
        loop_a = word("_loopCount")
        time.sleep(1.5)
        loop_b = word("_loopCount")
    except Exception as exc:                       # noqa: BLE001
        return SKIP, f"client not running: {exc}"

    if loop_a == loop_b:
        return FAIL, "client main loop is not running"
    if dropped or overruns:
        return FAIL, f"rx={rx} dropped={dropped} overruns={overruns}"
    return PASS, f"client alive, rx={rx}, 0 dropped, 0 overruns"


CHECKS = [
    ("unit", check_unit, False),
    ("coverage", check_coverage, False),
    ("render", check_render, False),
    ("emulator", check_emulator, True),
    ("hardware", check_hardware, True),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="skip the slow checks (emulator, hardware)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    results = []
    for name, fn, slow in CHECKS:
        if slow and args.quick:
            results.append((name, SKIP, "skipped (--quick)"))
            continue
        started = time.time()
        try:
            status, detail = fn()
        except Exception as exc:                   # noqa: BLE001
            status, detail = FAIL, f"{type(exc).__name__}: {exc}"
        results.append((name, status, detail, round(time.time() - started, 1)))

    if args.json:
        print(json.dumps([{"check": r[0], "status": r[1], "detail": r[2],
                           "seconds": r[3] if len(r) > 3 else None}
                          for r in results], indent=2))
    else:
        print(f"{'check':<12}{'result':<8}detail")
        print("-" * 74)
        for r in results:
            name, status, detail = r[0], r[1], r[2]
            secs = f" ({r[3]}s)" if len(r) > 3 else ""
            print(f"{name:<12}{status:<8}{detail}{secs}")
        failed = [r[0] for r in results if r[1] == FAIL]
        skipped = [r[0] for r in results if r[1] == SKIP]
        print()
        if failed:
            print(f"FAILED: {', '.join(failed)}")
        else:
            print("all executed checks passed")
        if skipped:
            print(f"not verified (skipped): {', '.join(skipped)}")

    return 1 if any(r[1] == FAIL for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
