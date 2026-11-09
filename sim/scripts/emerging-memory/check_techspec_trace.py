#!/usr/bin/env python3
"""Check a FASED metasim log against the technology-spec issuer rules.

TECHSPEC lines are printed when a request is admitted:

    TECHSPEC,<cycle>,<isWrite>,<addr>,<id>,<len>,<size>,<start>,<release>

The checker uses the same occupancy and release formulas as techspec.py.
It also records the simulator's target-cycle line. It does not treat
`release` as the target-visible AXI response: that response is later, after
the FASED egress and the functional backing memory.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

# Chisel printf pads each integer to its bit width, so fields contain spaces.
# The print bridge may also prefix "CYCLE: <n> ".
LINE = re.compile(
    r"(?:CYCLE:\s*(\d+)\s+)?"
    r"TECHSPEC,\s*(\d+)\s*,\s*(\d+)\s*,\s*([0-9a-fA-F]+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)"
)
CYCLES = re.compile(r"Target Cycles Emulated:\s*(\d+)")
PASSED = re.compile(r"\*\*\* PASSED \*\*\* after (\d+) cycles")


def occupancy(service: int, length: int) -> int:
    beats = length + 1
    return service if service > beats else beats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logfile")
    parser.add_argument("--read-latency", type=int, required=True)
    parser.add_argument("--write-latency", type=int, required=True)
    parser.add_argument("--read-service", type=int, required=True)
    parser.add_argument("--write-service", type=int, required=True)
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()

    events = []
    target_cycles = None
    passed_cycles = None
    with open(args.logfile) as handle:
        for raw in handle:
            line = raw.strip()
            match = LINE.search(line)
            if match:
                print_cycle, cycle, is_write, addr, axi_id, length, size, start, release = match.groups()
                events.append(
                    {
                        "print_cycle": int(print_cycle) if print_cycle is not None else None,
                        "cycle": int(cycle),
                        "is_write": int(is_write),
                        "addr": int(addr, 16),
                        "id": int(axi_id),
                        "length": int(length),
                        "size": int(size),
                        "start": int(start),
                        "release": int(release),
                    }
                )
                continue
            cyc = CYCLES.search(line)
            if cyc:
                target_cycles = int(cyc.group(1))
            ok = PASSED.search(line)
            if ok:
                passed_cycles = int(ok.group(1))

    errors = []
    if not events:
        errors.append("no TECHSPEC lines")
    print_cycle_mismatches = 0
    next_service = 0
    pending = []
    for index, event in enumerate(events):
        service = args.write_service if event["is_write"] else args.read_service
        latency = args.write_latency if event["is_write"] else args.read_latency
        occ = occupancy(service, event["length"])
        event["occupancy"] = occ
        expected_start = event["cycle"] if event["cycle"] > next_service else next_service
        # A same-cycle read is ordered first. If this event is a write and the
        # previous event was a read on this cycle, the read already advanced
        # next_service, so expected_start is that value.
        if event["start"] != expected_start:
            errors.append(
                f"line {index}: start {event['start']} != expected {expected_start}"
            )
        expected_release = event["start"] + latency - 1
        if event["release"] != expected_release:
            errors.append(
                f"line {index}: release {event['release']} != {expected_release}"
            )
        if event["start"] < event["cycle"]:
            errors.append(f"line {index}: start before admit cycle")
        if event["print_cycle"] is not None and event["print_cycle"] != event["cycle"]:
            print_cycle_mismatches += 1
        if pending and event["start"] < pending[-1][0] + pending[-1][1]:
            errors.append(f"line {index}: service window overlaps the previous op")
        pending.append((event["start"], occ))
        next_service = event["start"] + occ

    reads = sum(1 for event in events if not event["is_write"])
    writes = sum(1 for event in events if event["is_write"])
    summary = {
        "events": len(events),
        "reads": reads,
        "writes": writes,
        "target_cycles": target_cycles,
        "passed_cycles": passed_cycles,
        "print_cycle_mismatches": print_cycle_mismatches,
        "errors": errors,
    }
    text = json.dumps(summary, indent=2)
    if args.json_out:
        with open(args.json_out, "w") as handle:
            handle.write(text + "\n")
    print(text)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
