#!/usr/bin/env python3
"""Replay a captured HBMREQ CSV through the technology-spec reference.

The CSV cycles are the cycles on which the HBM model admitted each request.
This script offers those requests to a different timing model at the same
cycles and queues them if that model is not ready. It does not rerun the GPU,
the caches, or the HBM command scheduler. A longer service time therefore
stalls this open-loop schedule; a closed-loop core would have issued later
requests later as well.

AXI size is not in the HBMREQ trace. The Radiance FASED ports used for that
trace are 8-byte beats and the sample's axi_len is 3, so each request is
treated as four 8-byte beats (32 bytes) unless --axi-size is changed.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import subprocess
import sys
from collections import deque
from pathlib import Path

from techspec import Access, TechSpecModel, overlapping_services


SAMPLE = (
    Path(__file__).resolve().parents[1]
    / "hbm-validation"
    / "examples"
    / "radiance-memperf-reqtrace-sample.csv"
)
SPEC = Path(__file__).resolve().parent / "specs" / "illustrative_byte_addressable_nvm.json"


def load_requests(path: Path, axi_size: int) -> list[dict]:
    rows = []
    with path.open() as handle:
        for row in csv.DictReader(handle):
            rows.append(
                {
                    "cycle": int(row["cycle"]),
                    "rw": row["rw"],
                    "addr": int(row["addr"], 16),
                    "id": int(row["axi_id"]),
                    "length": int(row["axi_len"]),
                    "size": axi_size,
                }
            )
    if any(rows[i]["cycle"] > rows[i + 1]["cycle"] for i in range(len(rows) - 1)):
        raise SystemExit(f"{path} is not ordered by cycle")
    return rows


def replay(requests: list[dict], model: TechSpecModel) -> dict:
    read_q: deque[dict] = deque()
    write_q: deque[dict] = deque()
    index = 0
    wait_cycles = 0
    completed = []
    count = len(requests)

    def enqueue_due() -> None:
        nonlocal index
        while index < count and requests[index]["cycle"] <= model.t_cycle:
            if requests[index]["rw"] == "R":
                read_q.append(requests[index])
            elif requests[index]["rw"] == "W":
                write_q.append(requests[index])
            else:
                raise SystemExit(f"bad rw {requests[index]['rw']}")
            index += 1

    def as_access(item: dict) -> Access:
        return Access(item["addr"], item["id"], item["length"], item["size"])

    while True:
        enqueue_due()
        queued = bool(read_q or write_q)
        if not queued and index >= count and not model.has_inflight():
            break
        can_read = bool(read_q) and model.pending_reads < model.read_max
        can_write = (
            bool(write_q)
            and model.pending_aw < model.write_max
            and model.pending_w < model.write_max
        )
        if not can_read and not can_write:
            nxt = model._next_head_release()
            upcoming = requests[index]["cycle"] if index < count else None
            if nxt is None and upcoming is None:
                break
            if nxt is None:
                model.advance_to(upcoming)
                continue
            if upcoming is None or nxt < upcoming:
                if model.t_cycle < nxt:
                    model.advance_to(nxt)
                # Fall through and execute this cycle, which retires the head.
            elif model.t_cycle < upcoming:
                model.advance_to(upcoming)
                continue
        before = model.t_cycle
        # AW and W are one trace event. Offer them together only when both
        # channels can take a beat, so a lone W is never counted.
        result = model.step(
            ar=as_access(read_q[0]) if can_read else None,
            aw=as_access(write_q[0]) if can_write else None,
            w_last=can_write,
        )
        if result["accepted_read"]:
            admitted = read_q.popleft()
            wait_cycles += before - admitted["cycle"]
        if result["accepted_write"]:
            admitted = write_q.popleft()
            wait_cycles += before - admitted["cycle"]
        if result["completed_read"]:
            completed.append(result["completed_read"])
        if result["completed_write"]:
            completed.append(result["completed_write"])
        if model.t_cycle > requests[-1]["cycle"] + 10_000_000:
            raise SystemExit("replay did not drain")
    if read_q or write_q or index != count:
        raise SystemExit("replay dropped or failed to admit a request")
    overlaps = overlapping_services(model.schedule)
    if overlaps:
        raise SystemExit(f"issuer windows overlap: {overlaps[:3]}")
    reads = sum(1 for event in model.schedule if event["kind"] == "R")
    writes = sum(1 for event in model.schedule if event["kind"] == "W")
    last_release = max(event["release"] for event in model.schedule)
    span = last_release - requests[0]["cycle"] + 1
    busy = model.issuer_busy_cycles
    return {
        "requests": count,
        "reads": reads,
        "writes": writes,
        "device_read_bytes": model.device_read_bytes,
        "device_write_bytes": model.device_write_bytes,
        "logical_write_bytes": model.logical_write_bytes,
        "wait_cycles": wait_cycles,
        "issuer_busy_cycles": busy,
        "last_release_cycle": last_release,
        "schedule_span_cycles": span,
        "endurance_exceeded": model.endurance_exceeded,
        "retention_fresh_reads": model.retention_fresh_reads,
        "retention_stale_reads": model.retention_stale_reads,
        "retention_unknown_reads": model.retention_unknown_reads,
        "mean_wait_cycles": wait_cycles / count,
    }


def git_revision(repo: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, default=SAMPLE)
    parser.add_argument("--spec", type=Path, default=SPEC)
    parser.add_argument("--axi-size", type=int, default=3)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "research" / "emerging_memory" / "results",
    )
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text())
    requests = load_requests(args.trace, args.axi_size)
    lengths = sorted({row["length"] for row in requests})
    base = {
        "read_latency": spec["read_latency_cycles"],
        "write_latency": spec["write_latency_cycles"],
        "read_service_cycles": spec["read_service_cycles"],
        "write_service_cycles": spec["write_service_cycles"],
        "read_max": spec["outstanding_reads"],
        "write_max": spec["outstanding_writes"],
        "endurance_limit_bytes": spec["endurance_limit_bytes"],
        "retention_cycles": spec["retention_cycles"],
        "retention_sets": spec["retention_sets"],
        "retention_granularity_bytes": spec["retention_granularity_bytes"],
    }
    points = []
    for latency in (30, 200, 1000):
        for service in (1, 4, 32):
            for outstanding in (4, 32):
                model = TechSpecModel(
                    **{
                        **base,
                        "read_latency": latency,
                        "write_latency": latency,
                        "read_service_cycles": service,
                        "write_service_cycles": service,
                        "read_max": outstanding,
                        "write_max": outstanding,
                    }
                )
                stats = replay(requests, model)
                stats.update(
                    {
                        "read_latency": latency,
                        "write_latency": latency,
                        "service_cycles": service,
                        "outstanding": outstanding,
                    }
                )
                points.append(stats)
                print(
                    f"lat={latency:4d} svc={service:2d} out={outstanding:2d} "
                    f"wait={stats['wait_cycles']:8d} span={stats['schedule_span_cycles']:8d} "
                    f"busy={stats['issuer_busy_cycles']:8d}"
                )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[3]
    payload = {
        "firesim_commit": git_revision(repo),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "trace": str(args.trace),
        "trace_requests": len(requests),
        "trace_first_cycle": requests[0]["cycle"],
        "trace_last_offer_cycle": requests[-1]["cycle"],
        "axi_lengths_present": lengths,
        "axi_size_assumed": args.axi_size,
        "spec": spec,
        "assumption": (
            "Open-loop replay of the checked-in Radiance MemPerf HBMREQ sample. "
            "Not a GPU rerun and not an FPGA result. Service and latency values "
            "other than the illustrative defaults are sensitivity inputs."
        ),
        "points": points,
    }
    out_json = args.out_dir / "techspec_sample_sensitivity.json"
    out_json.write_text(json.dumps(payload, indent=2) + "\n")
    write_figure(points, args.out_dir / "techspec_sample_sensitivity.png")
    print(f"wrote {out_json}")


def write_figure(points: list[dict], path: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib is not installed; skipped the sensitivity figure")
        return
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.6))
    for service, style in ((1, "o-"), (4, "s-"), (32, "^-")):
        rows = [p for p in points if p["service_cycles"] == service and p["outstanding"] == 32]
        rows.sort(key=lambda p: p["read_latency"])
        axes[0].plot(
            [p["read_latency"] for p in rows],
            [p["wait_cycles"] / p["requests"] for p in rows],
            style,
            label=f"service {service}",
        )
    for outstanding, style in ((4, "o-"), (32, "s-")):
        rows = [p for p in points if p["outstanding"] == outstanding and p["service_cycles"] == 4]
        rows.sort(key=lambda p: p["read_latency"])
        axes[1].plot(
            [p["read_latency"] for p in rows],
            [p["wait_cycles"] / p["requests"] for p in rows],
            style,
            label=f"outstanding {outstanding}",
        )
    axes[0].set_title("Outstanding cap 32")
    axes[1].set_title("Programmed service 4")
    for axis in axes:
        axis.set_xlabel("Programmed read and write latency (target cycles)")
        axis.set_ylabel("Mean cycles waited before admit")
        axis.set_xscale("log")
        axis.grid(True, which="both", alpha=0.3)
        axis.legend(frameon=False)
    fig.suptitle("Open-loop MemPerf sample on the technology-spec model", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
