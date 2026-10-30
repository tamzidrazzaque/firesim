#!/usr/bin/env python3
"""Replay INDCMD/INDREF lines through the independent Python device.

FASED cycles are the model's programmed tCK; choose the matching profile.
A command the scheduler emitted is legal when the device accepts it.
The device does not move an early command forward.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "independent"))

from rpc_fased.device import Activate, Precharge, Read, Refresh, RpcDram, Write
from rpc_fased.params import GEOMETRY
from rpc_fased.profiles import profile_for

CMD = re.compile(r"INDCMD,\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)")
REF = re.compile(r"INDREF,\s*(\d+),\s*(\d+)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--tck-ps", type=int, default=1250)
    parser.add_argument("--cl", type=int, default=11)
    parser.add_argument("--page-policy", choices=("open", "closed"), default="open")
    args = parser.parse_args()
    path = args.log
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
    if not events:
        print(f"no INDCMD or INDREF events in {path}", file=sys.stderr)
        return 1
    events.sort(key=lambda item: (item[0], 0 if item[1] == "ref" else 1))
    profile = profile_for(args.tck_ps, cl=args.cl)
    dev = RpcDram(page_policy=args.page_policy, timing=profile, refresh_occupancy="row_step")
    ready = dev.initialize(cl=args.cl, nwr=profile.nWR_MIN)
    bad = 0
    counts: dict[str, int] = {}
    for cycle, kind, payload in events:
        if cycle < ready:
            print(f"early-trace {kind} at {cycle} before init ready {ready}")
            bad += 1
            continue
        if kind == "ref":
            (stall,) = payload
            window = GEOMETRY.rows * profile.tREFI_FST * 4
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
    print(f"tck_ps={profile.tck_ps} cl={profile.CL} page_policy={args.page_policy} "
          f"events={len(events)} counts={counts} violations={bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
