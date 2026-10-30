#!/usr/bin/env python3
"""Replay observed ETH pin commands through the frozen Chisel checker.

The pin log supplies the cycle and the 32-bit packet exactly as printed by
rpc_pin_memory. The Chisel program is the one produced in the isolated
workspace. This script does not move an early command to a later cycle.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "independent"))

from rpc_fased.check import parse_pin_log, replay  # noqa: E402
from rpc_fased.profiles import profile_for  # noqa: E402

PIN_CMD = re.compile(r"RPC_PIN_CMD cycle=(\d+) packet=([0-9a-fA-F]+)")
SV_VIO = re.compile(
    r"^RPC_TIMING_VIOLATION constraint=(\S+) offered=(\d+) earliest=(\d+)",
    re.M,
)
CHISEL_LINE = re.compile(
    r"^(ACCEPT|VIOLATION|INTERPRETATION)\s+(.*)$"
)


def to_checker_packet(pin_packet: int) -> int:
    """Match docs/PACKET.md in the frozen checker.

    The pin log stores {rising beat, falling beat}, so the rising sample
    is in bits [31:16]. The checker stores the rising sample in bits
    [15:0]. The two 16-bit halves are exchanged and no bit inside a beat
    is changed.
    """
    rise = (pin_packet >> 16) & 0xFFFF
    fall = pin_packet & 0xFFFF
    return (fall << 16) | rise


def pin_records(text: str) -> list[dict[str, object]]:
    records = []
    for match in PIN_CMD.finditer(text):
        packet = to_checker_packet(int(match.group(2), 16))
        records.append(
            {
                "cycle": int(match.group(1)),
                "packet_hex": f"{packet:08x}",
            }
        )
    return records


def write_jsonl(records: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as stream:
        for record in records:
            stream.write(json.dumps(record, sort_keys=True) + "\n")


def parse_chisel(text: str) -> list[dict[str, str]]:
    rows = []
    for line in text.splitlines():
        match = CHISEL_LINE.match(line.strip())
        if match is None:
            continue
        fields = {"kind": match.group(1)}
        for part in match.group(2).split():
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            fields[key] = value
        rows.append(fields)
    return rows


def run_chisel(
    cleanroom: Path,
    jsonl: Path,
    tck_ps: int,
    refresh_select: int,
    log_path: Path,
) -> list[dict[str, str]]:
    env = os.environ.copy()
    env["JAVA_HOME"] = "/usr/lib/jvm/java-11-openjdk-amd64"
    env["JAVA_TOOL_OPTIONS"] = f"-Djava.io.tmpdir={cleanroom / 'tmp'}"
    env["PATH"] = f"{cleanroom / 'tools' / 'sbt' / 'bin'}:{env.get('PATH', '')}"
    env["HOME"] = str(cleanroom / "home")
    env["TMPDIR"] = str(cleanroom / "tmp")
    env["SBT_OPTS"] = (
        f"-Dsbt.global.base={cleanroom / 'home' / '.sbt'} "
        f"-Dsbt.boot.directory={cleanroom / 'home' / '.sbt' / 'boot'} "
        f"-Dsbt.ivy.home={cleanroom / 'home' / '.ivy2'} "
        f"-Djava.io.tmpdir={cleanroom / 'tmp'} -Xms512M -Xmx2G"
    )
    command = [
        "sbt",
        "-batch",
        f"runMain rpc.Replay --tck-ps {tck_ps} --refresh-select {refresh_select} {jsonl}",
    ]
    completed = subprocess.run(
        command,
        cwd=cleanroom,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(completed.stdout)
    if completed.returncode != 0:
        raise RuntimeError(f"chisel replay failed, log {log_path}")
    rows = parse_chisel(completed.stdout)
    if not rows:
        raise RuntimeError(f"no checker lines in {log_path}")
    return rows


def python_rows(text: str, mode: str, tck_ps: int) -> list[dict[str, object]]:
    observed = parse_pin_log(text)
    _, reports, _ = replay(observed, profile_for(tck_ps, cl=8), refresh_occupancy=mode)
    return [
        {
            "constraint": report.constraint,
            "offered_cycle": report.offered_cycle,
            "earliest_legal_cycle": report.earliest_legal_cycle,
            "command": report.command,
        }
        for report in reports
    ]


def mutate(records: list[dict[str, object]], index: int, delta: int) -> list[dict[str, object]]:
    mutated = [dict(record) for record in records]
    mutated[index]["cycle"] = int(mutated[index]["cycle"]) + delta
    return mutated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--cleanroom", type=Path, required=True)
    parser.add_argument("--tck-ps", type=int, default=5000)
    parser.add_argument("--refresh-select", type=int, default=0)
    parser.add_argument("--python-mode", default="row_step")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results/differential/chisel-replay",
    )
    parser.add_argument("--skip-chisel", action="store_true")
    args = parser.parse_args()
    summary = []
    for log in args.logs:
        text = log.read_text(errors="replace")
        records = pin_records(text)
        if not records:
            raise SystemExit(f"no pin commands in {log}")
        jsonl = args.output_dir / f"{log.stem}.jsonl"
        write_jsonl(records, jsonl)
        item: dict[str, object] = {
            "trace": log.name,
            "commands": len(records),
            "jsonl": str(jsonl),
            "sv_violations": [
                {
                    "constraint": constraint,
                    "offered_cycle": int(offered),
                    "earliest_legal_cycle": int(earliest),
                }
                for constraint, offered, earliest in SV_VIO.findall(text)
            ],
            "python": python_rows(text, args.python_mode, args.tck_ps),
        }
        if not args.skip_chisel:
            rows = run_chisel(
                args.cleanroom,
                jsonl,
                args.tck_ps,
                args.refresh_select,
                args.output_dir / f"{log.stem}.chisel.txt",
            )
            item["chisel"] = rows
            item["chisel_violations"] = [
                row for row in rows if row["kind"] != "ACCEPT"
            ]
        summary.append(item)
        chisel_n = len(item.get("chisel_violations", []))
        print(
            f"{log.name}: commands={len(records)} "
            f"python={len(item['python'])} sv={len(item['sv_violations'])} "
            f"chisel={chisel_n}"
        )
    report = args.output_dir / "summary.json"
    report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
