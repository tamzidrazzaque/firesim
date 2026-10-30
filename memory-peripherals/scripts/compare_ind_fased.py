#!/usr/bin/env python3
"""Replay INDCMD/INDREF lines through the independent Python device.

FASED cycles are the model's tCK. This is not the 5 ns ETH pin clock.
A command the scheduler emitted is legal when the device accepts it.
The device does not move an early command forward.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path("/scratch/trazzaque/memory-peripherals")
sys.path.insert(0, str(ROOT / "independent"))

from rpc_fased.device import Activate, Precharge, Read, Refresh, RpcDram, Write
from rpc_fased.params import GEOMETRY, P

CMD = re.compile(r"INDCMD,\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)")
REF = re.compile(r"INDREF,\s*(\d+),\s*(\d+)")


def main() -> int:
    path = Path(sys.argv[1])
    text = path.read_text(errors="replace")
    events: list[tuple[int, str, tuple]] = []
    for line in text.splitlines():
        cmd = CMD.search(line)
        if cmd:
            cycle, op, bank, row = (int(cmd.group(i)) for i in range(1, 5))
            events.append((cycle, "cmd", (op, bank, row)))
            continue
        ref = REF.search(line)
        if ref:
            events.append((int(ref.group(1)), "ref", (int(ref.group(2)),)))
    events.sort(key=lambda item: (item[0], 0 if item[1] == "ref" else 1))
    dev = RpcDram(page_policy="open", refresh_occupancy="row_step")
    ready = dev.initialize()
    bad = 0
    counts: dict[str, int] = {}
    for cycle, kind, payload in events:
        if cycle < ready:
            print(f"early-trace {kind} at {cycle} before init ready {ready}")
            bad += 1
            continue
        if kind == "ref":
            (stall,) = payload
            window = GEOMETRY.rows * P.tREFI_FST * 4
            if stall != window:
                print(f"refresh stall {stall} != row-step {window}")
                bad += 1
            result = dev.issue(Refresh(cycle, banks=(0, 1, 2, 3)))
            counts["refresh"] = counts.get("refresh", 0) + 1
        else:
            op, bank, row = payload
            if op == 1:
                result = dev.issue(Activate(cycle, bank, row))
                counts["activate"] = counts.get("activate", 0) + 1
            elif op == 2:
                result = dev.issue(Precharge(cycle, bank))
                counts["precharge"] = counts.get("precharge", 0) + 1
            elif op == 3:
                result = dev.issue(Read(cycle, bank, 0))
                counts["read"] = counts.get("read", 0) + 1
            elif op == 4:
                result = dev.issue(Write(cycle, bank, 0, bytes(32)))
                counts["write"] = counts.get("write", 0) + 1
            else:
                print(f"unknown op {op}")
                bad += 1
                continue
        if not result.accepted:
            bad += 1
            if bad <= 12:
                print(f"reject {kind} {payload} at {cycle}: {result.violations}")
    print(f"events={len(events)} counts={counts} violations={bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
