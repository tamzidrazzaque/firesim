#!/usr/bin/env python3
"""Modeled performance of HyperRAM and RPC DRAM.

Numbers are memory-clock cycles converted with the programmed tCK. They are
not FPGA measurements and they are not host simulation throughput.
"""

from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from memperiph.hyperram import (  # noqa: E402
    HyperRAMFased,
    HyperRAMParams,
    theoretical_bandwidth_MBps as hyper_peak,
)
from memperiph.rpcdram import (  # noqa: E402
    RpcDramFased,
    profile_1600,
    profile_200mhz,
    theoretical_bandwidth_MBps as rpc_peak,
)
from memperiph.util import AxiRequest  # noqa: E402

OUT = ROOT / "results" / "characterization"
SEED = 20261016


def mbps(nbytes: int, cycles: int, tck_ps: int) -> float:
    if cycles <= 0:
        return 0.0
    return (nbytes / cycles) * (1e12 / tck_ps) / 1e6


def summarize(name, model, config, tck_ps, peak, completions, nbytes, extra=None):
    if not completions:
        raise RuntimeError(name)
    start = min(c.accept_cycle for c in completions)
    end = max(c.done_cycle for c in completions)
    cycles = max(1, end - start)
    read_l = sorted(c.latency for c in completions if not c.is_write)
    write_l = sorted(c.latency for c in completions if c.is_write)

    def pct(xs, p):
        if not xs:
            return ""
        k = min(len(xs) - 1, int(round((p / 100) * (len(xs) - 1))))
        return xs[k]

    row = {
        "workload": name,
        "model": model,
        "config": config,
        "tCK_ps": tck_ps,
        "nbytes": nbytes,
        "transactions": len(completions),
        "cycles": cycles,
        "read_latency_ck_p50": pct(read_l, 50),
        "write_latency_ck_p50": pct(write_l, 50),
        "bandwidth_MBps": round(mbps(nbytes, cycles, tck_ps), 3),
        "theoretical_peak_MBps": round(peak, 3),
        "efficiency": round(mbps(nbytes, cycles, tck_ps) / peak, 4) if peak else "",
        "source": "python reference model, not silicon",
    }
    if extra:
        row.update(extra)
    return row


def hyper_variable() -> HyperRAMParams:
    p = HyperRAMParams()
    # CR0 latency code 7, variable latency, legacy linear/wrapped.
    p.cr0_reset = 0x8F27
    return p


def run_hyper(params, label, requests, outstanding):
    m = HyperRAMFased(params)
    # The power-on CR0 is already the requested mode; drop the history of
    # reset so it does not affect the trace the caller sees.
    done = m.run(requests, outstanding=outstanding)
    return done, m


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    rows = []

    # --- HyperRAM latency and burst sweep (variable latency, 200 MHz) ---
    hv = hyper_variable()
    for n in (2, 16, 32, 64, 128, 256, 512, 1024, 2048):
        data = bytes([0xA5]) * n
        wr = run_hyper(hv, "wr", [AxiRequest(True, 0, n, data=data)], 1)[0]
        rd = run_hyper(hv, "rd", [AxiRequest(False, 0, n)], 1)[0]
        rows.append(summarize(
            f"hyperram_var_write_{n}B", "hyperram", "S80KS2562 200MHz variable L=7",
            hv.tck_ps, hyper_peak(hv), wr, n))
        rows.append(summarize(
            f"hyperram_var_read_{n}B", "hyperram", "S80KS2562 200MHz variable L=7",
            hv.tck_ps, hyper_peak(hv), rd, n))

    # Fixed-latency power-on default, same sizes, reads only.
    hf = HyperRAMParams()
    for n in (32, 256, 2048):
        rd = run_hyper(hf, "rd", [AxiRequest(False, 0, n)], 1)[0]
        rows.append(summarize(
            f"hyperram_fixed_read_{n}B", "hyperram", "S80KS2562 200MHz fixed 2x L=7",
            hf.tck_ps, hyper_peak(hf), rd, n))

    # Random 32 B reads inside 64 KiB, one outstanding (latency) and 8 (queued).
    for outstanding, tag in ((1, "lat"), (8, "queued")):
        reqs = []
        for i in range(64):
            addr = (rng.randrange(0, 64 * 1024 - 32)) & ~1
            reqs.append(AxiRequest(False, addr, 32, xid=i))
        done = run_hyper(hv, tag, reqs, outstanding)[0]
        rows.append(summarize(
            f"hyperram_random32B_{tag}", "hyperram", "S80KS2562 200MHz variable L=7",
            hv.tck_ps, hyper_peak(hv), done, 64 * 32,
            {"outstanding": outstanding, "seed": SEED}))

    # Mixed 50/50 sequential.
    mix = []
    for i in range(32):
        addr = i * 64
        if i % 2 == 0:
            mix.append(AxiRequest(True, addr, 64, xid=i, data=bytes([i & 0xFF]) * 64))
        else:
            mix.append(AxiRequest(False, addr, 64, xid=i))
    done = run_hyper(hv, "mix", mix, 4)[0]
    rows.append(summarize(
        "hyperram_seq_mix_64B", "hyperram", "S80KS2562 200MHz variable L=7",
        hv.tck_ps, hyper_peak(hv), done, 32 * 64, {"outstanding": 4, "mix": "50/50"}))

    # --- RPC DRAM ---
    for prof, name in ((profile_1600(), "rpc1600"), (profile_200mhz(), "rpc200")):
        peak = rpc_peak(prof)
        cfg = f"EM6GA16L tCK={prof.tck_ps}ps CL={prof.cl} RL={prof.rl_ck}"
        for page in ("open", "closed"):
            m = RpcDramFased(prof, page=page)
            n = 2048
            done = m.run([AxiRequest(False, 0, n)], outstanding=8)
            rows.append(summarize(
                f"{name}_{page}_seq_{n}B", "rpc-dram", cfg + f" {page}-page",
                prof.tck_ps, peak, done, n))
            # 32 separate 32 B reads along one row. Closed page pays ACT/PRE
            # on every one; open page streams them.
            m = RpcDramFased(prof, page=page)
            seq = [AxiRequest(False, i * 32, 32, xid=i) for i in range(32)]
            done = m.run(seq, outstanding=8)
            rows.append(summarize(
                f"{name}_{page}_seq32x32B", "rpc-dram", cfg + f" {page}-page",
                prof.tck_ps, peak, done, 32 * 32, {"outstanding": 8}))
            # Random 32 B inside 32 rows (64 KiB): row misses, same bank.
            rng2 = random.Random(SEED)
            reqs = []
            for i in range(48):
                row = rng2.randrange(0, 32)
                reqs.append(AxiRequest(False, row * 2048, 32, xid=i))
            m = RpcDramFased(prof, page=page)
            done = m.run(reqs, outstanding=4)
            rows.append(summarize(
                f"{name}_{page}_random_row_32B", "rpc-dram", cfg + f" {page}-page",
                prof.tck_ps, peak, done, 48 * 32,
                {"outstanding": 4, "seed": SEED}))

    # One full-chip fast refresh, reported as a stall rather than bandwidth.
    m = RpcDramFased(profile_1600(), page="open", refresh=True)
    m.next_refresh = 0
    m.run([AxiRequest(False, 0, 32)])
    rows.append({
        "workload": "rpc1600_fst_refresh_all_banks",
        "model": "rpc-dram",
        "config": "EM6GA16L speed-1600 one-shot FST refresh, 4 banks",
        "tCK_ps": 1250,
        "nbytes": 0,
        "transactions": 1,
        "cycles": m.refresh_stall,
        "read_latency_ck_p50": "",
        "write_latency_ck_p50": "",
        "bandwidth_MBps": "",
        "theoretical_peak_MBps": round(rpc_peak(), 3),
        "efficiency": "",
        "source": "python reference model, not silicon",
        "refresh_stall_ck": m.refresh_stall,
        "refresh_stall_us": round(m.refresh_stall * 1250 / 1e6, 3),
    })

    # Published HBM2-2400 channel ceiling, for scale. Not re-simulated here.
    rows.append({
        "workload": "hbm2_2400_channel_peak_published",
        "model": "hbm2",
        "config": "JESD235 128-bit channel at 2.4 Gbps/pin, one channel",
        "tCK_ps": 833,
        "nbytes": "",
        "transactions": "",
        "cycles": "",
        "read_latency_ck_p50": "",
        "write_latency_ck_p50": "",
        "bandwidth_MBps": 38400.0,
        "theoretical_peak_MBps": 38400.0,
        "efficiency": 1.0,
        "source": "pin-rate ceiling from the existing HBM notes, not a new simulation",
    })

    fieldnames = []
    for row in rows:
        for k in row:
            if k not in fieldnames:
                fieldnames.append(k)
    csv_path = OUT / "performance.csv"
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    plot_burst(rows)
    plot_compare(rows)
    print(f"wrote {csv_path}")
    for row in rows:
        if row["workload"] in (
            "hyperram_var_read_32B",
            "hyperram_var_read_2048B",
            "hyperram_fixed_read_32B",
            "rpc1600_open_seq_2048B",
            "rpc1600_closed_seq_2048B",
            "rpc1600_open_seq32x32B",
            "rpc1600_closed_seq32x32B",
            "rpc200_open_seq_2048B",
            "rpc1600_fst_refresh_all_banks",
        ) or "random" in row["workload"]:
            print(f"{row['workload']}: bw={row['bandwidth_MBps']} MB/s "
                  f"lat={row['read_latency_ck_p50']} ck eff={row['efficiency']}")


def plot_burst(rows) -> None:
    xs, ys = [], []
    for row in rows:
        name = row["workload"]
        if name.startswith("hyperram_var_read_") and name.endswith("B"):
            xs.append(int(name.split("_")[-1][:-1]))
            ys.append(row["bandwidth_MBps"])
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(xs, ys, marker="o", label="variable latency")
    fx, fy = [], []
    for row in rows:
        name = row["workload"]
        if name.startswith("hyperram_fixed_read_"):
            fx.append(int(name.split("_")[-1][:-1]))
            fy.append(row["bandwidth_MBps"])
    ax.plot(fx, fy, marker="s", label="fixed 2x latency")
    ax.axhline(400, color="gray", linestyle="--", label="400 MB/s pin ceiling")
    ax.set_xscale("log", base=2)
    ax.set_xlabel("Read size (bytes)")
    ax.set_ylabel("Modeled bandwidth (MB/s)")
    ax.set_title("HyperRAM S80KS2562-class, 200 MHz, one outstanding read")
    ax.legend()
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "hyperram_burst_bandwidth.png", dpi=120)
    plt.close(fig)


def plot_compare(rows) -> None:
    wanted = [
        "hyperram_var_read_2048B",
        "rpc200_open_seq32x32B",
        "rpc200_closed_seq32x32B",
        "rpc1600_open_seq32x32B",
        "rpc1600_closed_seq32x32B",
    ]
    labels, vals = [], []
    for name in wanted:
        for row in rows:
            if row["workload"] == name:
                labels.append(name.replace("_", "\n"))
                vals.append(row["bandwidth_MBps"])
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(range(len(vals)), vals, color=["#4c78a8", "#f58518", "#e45756", "#54a24b", "#b279a2"])
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Modeled bandwidth (MB/s)")
    ax.set_title("Sequential 2 KiB read, modeled (not measured)")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "sequential_compare.png", dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    main()
