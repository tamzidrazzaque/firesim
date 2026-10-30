#!/usr/bin/env python3
"""Replay saved pin commands without changing their issue cycles.

The JSONL export contains the raw packet and its decoded fields so another
device model can consume the same observed controller trace. The two refresh
readings are reported separately because the datasheet does not state tRFC.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "independent"))

from rpc_fased.check import parse_pin_log, replay
from rpc_fased.profiles import profile_for

DEFAULT_TRACES = {
    "eth_full_pin_run.log": (21, 0, 0),
    "chipyard_eth_timing_rocket_stdout.log": (394, 0, 0),
    "chipyard_eth_timing_boom_stdout.log": (409, 0, 0),
    "eth_timing_directed_run.log": (57, 0, 0),
    "eth_timing_directed_negative.log": (45, 1, 1),
    "eth_timing_directed_borderline.log": (45, 0, 1),
}
OBSERVER_VIOLATION = re.compile(
    r"^RPC_TIMING_VIOLATION constraint=(\S+) offered=(\d+) earliest=(\d+)", re.M
)


def export_record(item: object) -> dict[str, object]:
    cmd = item.command
    return {
        "cycle": item.cycle,
        "packet_hex": f"{item.packet:08x}",
        "kind": cmd.kind,
        "bank": cmd.bank,
        "row": cmd.row,
        "column": cmd.column if cmd.kind in ("read", "write") else None,
        "burst_count": cmd.burst_count if cmd.kind in ("read", "write") else None,
        "banks": cmd.banks if cmd.kind == "refresh" else None,
        "refop": cmd.refop if cmd.kind == "refresh" else None,
        "cl": cmd.cl if cmd.kind == "mrs" else None,
        "nwr": cmd.nwr if cmd.kind == "mrs" else None,
    }


def verify(path: Path, output_dir: Path, expected: tuple[int, int, int] | None) -> dict:
    raw = path.read_bytes()
    decoded = raw.decode(errors="replace")
    observed = parse_pin_log(decoded)
    if not observed:
        raise ValueError(f"no RPC_PIN_CMD lines in {path}")
    if any(right.cycle < left.cycle for left, right in zip(observed, observed[1:])):
        raise ValueError(f"nonmonotonic pin cycles in {path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    export_path = output_dir / f"{path.stem}.jsonl"
    with export_path.open("w") as stream:
        for item in observed:
            stream.write(json.dumps(export_record(item), sort_keys=True) + "\n")

    profile = profile_for(5000, cl=8)
    results = {}
    for mode in ("one_trefi", "row_step"):
        _, reports, counts = replay(observed, profile, refresh_occupancy=mode)
        results[mode] = {
            "counts": counts,
            "violations": [
                {
                    "constraint": report.constraint,
                    "offered_cycle": report.offered_cycle,
                    "earliest_legal_cycle": report.earliest_legal_cycle,
                    "command": report.command,
                    "detail": report.detail,
                }
                for report in reports
            ],
        }
    observer = [
        {"constraint": constraint, "offered_cycle": int(offered),
         "earliest_legal_cycle": int(earliest)}
        for constraint, offered, earliest in OBSERVER_VIOLATION.findall(decoded)
    ]
    if observer:
        predicted = [
            {key: item[key] for key in ("constraint", "offered_cycle", "earliest_legal_cycle")}
            for item in results["row_step"]["violations"]
        ]
        if observer != predicted:
            raise ValueError(f"{path}: observer={observer}, independent={predicted}")
    summary = {
        "trace": path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "command_count": len(observed),
        "first_cycle": observed[0].cycle,
        "last_cycle": observed[-1].cycle,
        "activated_banks": sorted(
            {item.command.bank for item in observed if item.command.kind == "activate"}
        ),
        "observer_violations": observer,
        "independent": results,
        "export": str(export_path.relative_to(ROOT) if export_path.is_relative_to(ROOT) else export_path),
    }
    if expected is not None:
        count, one_violations, row_violations = expected
        if len(observed) != count:
            raise ValueError(f"{path}: {len(observed)} commands, expected {count}")
        for mode, violations in (("one_trefi", one_violations), ("row_step", row_violations)):
            actual = results[mode]["violations"]
            if len(actual) != violations:
                raise ValueError(f"{path} {mode}: {actual}")
            if violations:
                if {report["constraint"] for report in actual} != {"tREFI"}:
                    raise ValueError(f"{path} {mode}: wrong violation {actual}")
                if not all(
                    report["offered_cycle"] < report["earliest_legal_cycle"]
                    for report in actual
                ):
                    raise ValueError(f"{path} {mode}: early command was shifted {actual}")
        if observer:
            if len(observer) != row_violations:
                raise ValueError(f"{path}: SV observer {observer}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="*", type=Path, help="pin logs to replay")
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "results/differential/rpc-traces"
    )
    args = parser.parse_args()
    paths = args.logs or [ROOT / "results/logs" / name for name in DEFAULT_TRACES]
    report = []
    for path in paths:
        result = verify(path, args.output_dir, DEFAULT_TRACES.get(path.name))
        report.append(result)
        print(
            f"{path.name}: commands={result['command_count']} "
            f"banks={result['activated_banks']} "
            f"one_trefi={len(result['independent']['one_trefi']['violations'])} "
            f"row_step={len(result['independent']['row_step']['violations'])} "
            f"sv={len(result['observer_violations'])}"
        )
    report_path = args.output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
