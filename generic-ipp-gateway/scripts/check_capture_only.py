#!/usr/bin/env python3
"""Fail closed if application source grows a network/device output path."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
FORBIDDEN = re.compile(
    r"\b(socket|connect|sendto|sendmsg|writev|httpConnect2?|cupsConnectDest|"
    r"papplDeviceWrite|open_port|serialport)\s*\("
)
issues = []
for path in sorted(SOURCE.glob("*.c")):
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if FORBIDDEN.search(line):
            issues.append(f"{path.relative_to(ROOT)}:{number}: forbidden output API")

main = (SOURCE / "main.c").read_text()
capture = (SOURCE / "capture.c").read_text()
if '"127.0.0.1"' not in main:
    issues.append("main.c: listener must remain bound to loopback")
if '"capture://local"' not in capture:
    issues.append("capture.c: fixed capture URI missing")
if "return -1; /* The device interface is deliberately not an output path. */" not in capture:
    issues.append("capture.c: device write callback must remain unusable")

if issues:
    print("capture-only check failed:", *issues, sep="\n- ", file=sys.stderr)
    raise SystemExit(1)
print("capture-only source checks passed")
