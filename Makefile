# claude-c128
#
# make check   host-side tests and Unicode coverage        (no hardware)
# make emu     the real 6502 client in VICE                (no hardware)
# make emu64   the same client on an emulated C64            (no hardware)
# make eval    every layer, including hardware if present
# make disk    build the client and the autobooting D64
PYTHON ?= python3

.PHONY: help check test coverage emu eval client disk audit clean install-service emu64

help:
	@grep -E '^# make' Makefile | sed 's/^# /  /'

check: test coverage

test:
	$(PYTHON) server/test_bridge.py

coverage:
	$(PYTHON) tools/charaudit.py --strict

audit:
	$(PYTHON) tools/charaudit.py --gaps

client:
	$(MAKE) -C client

disk: client
	$(PYTHON) tools/mkbootdisk.py client/build/claude.prg \
	          -o client/build/claude-boot.d64

emu: disk
	$(PYTHON) tools/emutest.py --bootdisk client/build/claude-boot.d64 \
	          --command "bash --norc -i" --settle 20

# The C64 build has no boot sector: on real hardware the Ultimate's run_prg
# starts C64 mode directly, so there is nothing to autoboot from.
emu64: client
	$(PYTHON) tools/emutest.py --machine c64 \
	          --command "bash --norc -i" --settle 20

eval:
	$(PYTHON) tools/eval.py

install-service:
	install -Dm644 claude-c128.service \
	        $(HOME)/.config/systemd/user/claude-c128.service
	systemctl --user daemon-reload
	@echo "now: systemctl --user enable --now claude-c128"

clean:
	$(MAKE) -C client clean
	rm -f bridge.log hwbridge.log ptyraw.bin
	find . -name __pycache__ -type d -exec rm -rf {} +
