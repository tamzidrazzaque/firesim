#!/usr/bin/env python3
"""Replay a FASED HBM command trace against Ramulator 2.1's HBM2 device model.

Ramulator (pinned commit b30320bc9385b708e86b67ebb9f48858cc66d798) is used as
an *independent timing-legality checker*: every command the FASED HBM model
issued is replayed, at the cycle it was issued, into Ramulator's HBM2 device
(C++ engine via the nanobind test harness). Ramulator evaluates its own
JESD235 timing constraints and state machine; any command that Ramulator
considers not-ready at that cycle is reported as a violation.

This is a timing-LEGALITY comparison, not a claim of cycle-identical
scheduling: FASED and Ramulator's own controller may (and do) make different
scheduling decisions; what is checked is that FASED never issues a command
earlier than the JESD235 timing rules allow, and never issues a command that
is illegal for the current bank state.

Notes on the mapping:
  - FASED prints the pseudo channel in the monitor's `rank` position.
  - FASED bank addresses carry the bank group in the LOW 2 bits.
  - FASED reads/writes with autoPRE map to RDA/WRA.
  - FASED refresh(pc) is an all-bank refresh of one pseudo channel -> REFab.
  - FASED refsb(pc, bank) -> REFpb.
  - RD/WR rows are reconstructed from the preceding ACT to the same bank.
  - Known conservative-in-FASED differences (cannot cause false PASSes):
    FASED counts REFSB in the tFAW window and spaces REFSB-to-REFSB by
    tRREFD; Ramulator does not require either.

Usage:
  RAMULATOR2_DIR=/path/to/ramulator2 ./check_trace_ramulator.py trace.csv
"""

import argparse
import csv
import os
import sys
from collections import defaultdict


def import_harness(ramulator_dir):
    sys.path.insert(0, os.path.join(ramulator_dir, "python"))
    sys.path.insert(0, ramulator_dir)  # for the `tests` package
    import ramulator  # noqa: F401
    from tests.device_timings import harness
    return ramulator, harness


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("trace", help="CSV from parse_fased_trace.py")
    ap.add_argument("--ramulator", default=os.environ.get("RAMULATOR2_DIR"),
                    help="path to the pinned ramulator2 checkout")
    ap.add_argument("--org", default="HBM2_8Gb")
    ap.add_argument("--timing", default="HBM2_2400Mbps")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    if not args.ramulator:
        sys.exit("Set RAMULATOR2_DIR or pass --ramulator")

    rml, harness = import_harness(args.ramulator)
    dram = rml.dram.HBM2(org_preset=args.org, timing_preset=args.timing)
    dut = harness.DeviceUnderTest(dram)
    max_rows = dut.org["row"]

    with open(args.trace) as f:
        trace = [
            {k: int(v) if k != "cmd" else v for k, v in row.items()}
            for row in csv.DictReader(f)
        ]

    open_row = {}  # (pc, bank) -> row opened by the last ACT
    n_checked = 0
    violations = []

    for t in trace:
        pc, bank, cyc = t["pc"], t["bank"], t["cycle"]
        cmd = t["cmd"]
        if cmd == "ACT":
            open_row[(pc, bank)] = t["row"]
            row = t["row"]
        elif cmd in ("RD", "WR", "PRE"):
            row = open_row.get((pc, bank), 0)
        else:
            row = 0

        if cmd == "RD":
            rcmd = "RDA" if t["autopre"] else "RD"
        elif cmd == "WR":
            rcmd = "WRA" if t["autopre"] else "WR"
        elif cmd == "PRE":
            rcmd = "PREpb"
        else:
            rcmd = cmd  # ACT / REFab / REFpb

        if cmd == "REFab":
            addr = dut.addr_vec(PseudoChannel=pc, BankGroup=dut.ALL,
                                Bank=dut.ALL, Row=dut.ALL)
        else:
            addr = dut.addr_vec(
                PseudoChannel=pc,
                BankGroup=t["bankgroup"],
                Bank=t["bank_in_group"],
                Row=row % max_rows,
            )

        p = dut.probe(rcmd, addr, clk=cyc)
        n_checked += 1
        if p.ready:
            dut.issue(rcmd, addr, clk=cyc)
            if args.verbose:
                print(f"ok   {cyc:>8} {rcmd:<5} pc={pc} bank={bank} row={row}")
        else:
            violations.append((cyc, rcmd, pc, bank, row, p))
            print(f"VIOLATION @ {cyc}: {rcmd} pc={pc} bank={bank} row={row} "
                  f"(ramulator: preq={p.preq}, timing_OK={p.timing_OK}, "
                  f"row_open={p.row_open}, row_hit={p.row_hit})")

    counts = defaultdict(int)
    for t in trace:
        counts[t["cmd"]] += 1
    print(f"\n{args.trace}: checked {n_checked} commands "
          f"({dict(counts)}) against Ramulator {args.timing}/{args.org}: "
          f"{len(violations)} violations")
    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
