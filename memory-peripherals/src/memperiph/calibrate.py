"""Compare a trace with the model and fit a small set of timing parameters.

This is the software half of a later FPGA measurement loop. It has been
exercised only on traces the model itself generated. Those runs show that
the fitter can recover a known parameter. They are not measurements of a
physical HyperRAM or RPC DRAM device.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace

from .hyperram import HyperRAMDevice, HyperRAMParams, HyperTxn
from .rpcdram import RpcDramParams


@dataclass
class Observation:
    """One host-visible transfer, in memory-clock cycles."""

    kind: str
    addr: int
    nbytes: int
    start_ck: int
    first_data_ck: int
    end_ck: int
    rwds_high: bool | None = None
    gap_before_ck: int | None = None
    row_hit: bool | None = None

    @staticmethod
    def from_hyper(txn: HyperTxn, prev_end: int | None) -> "Observation":
        gap = None if prev_end is None else txn.start - prev_end
        return Observation(
            kind="write" if txn.is_write else "read",
            addr=txn.addr, nbytes=txn.nbytes, start_ck=txn.start,
            first_data_ck=txn.first_data, end_ck=txn.done,
            rwds_high=txn.rwds_high, gap_before_ck=gap,
        )


@dataclass
class Mismatch:
    index: int
    field: str
    expected: int
    observed: int

    def __str__(self) -> str:
        return f"[{self.index}] {self.field}: model {self.expected} observed {self.observed}"


def recover_hyperram_latency(obs: list[Observation], ca_ck: int = 3) -> int:
    """Recover the base initial-latency (not the doubled value).

    A transaction with RWDS low during CA has ``first - start - CA = L``.
    A transaction with RWDS high has ``first - start - CA = 2L``.
    """
    votes: list[int] = []
    for o in obs:
        if o.nbytes <= 0:
            continue
        delta = o.first_data_ck - o.start_ck - ca_ck
        if delta <= 0:
            continue
        if o.rwds_high:
            if delta % 2 == 0:
                votes.append(delta // 2)
        else:
            votes.append(delta)
    if not votes:
        raise ValueError("no latency samples")
    return Counter(votes).most_common(1)[0][0]


def recover_min_gap(obs: list[Observation]) -> int:
    """Smallest observed CS# high gap. That is tCSHI when same-direction traffic dominates."""
    gaps = [o.gap_before_ck for o in obs if o.gap_before_ck is not None and o.gap_before_ck >= 0]
    if not gaps:
        raise ValueError("no gaps")
    return min(gaps)


def recover_rpc_rl(row_hit_latencies: list[int]) -> int:
    """Open-page row-hit read latency is RL when the command bus is idle."""
    if not row_hit_latencies:
        raise ValueError("no row-hit samples")
    return Counter(row_hit_latencies).most_common(1)[0][0]


def hyperram_mismatches(reference: list[Observation], measured: list[Observation],
                        *, tol_ck: int = 0) -> list[Mismatch]:
    if len(reference) != len(measured):
        raise ValueError("trace lengths differ")
    out = []
    for i, (ref, got) in enumerate(zip(reference, measured)):
        for field in ("first_data_ck", "end_ck"):
            exp = getattr(ref, field)
            obs = getattr(got, field)
            # Compare the latency relative to the start, so a time offset
            # common to a whole trace does not look like a model error.
            exp_rel = exp - ref.start_ck
            obs_rel = obs - got.start_ck
            if abs(exp_rel - obs_rel) > tol_ck:
                out.append(Mismatch(i, field, exp_rel, obs_rel))
        if ref.rwds_high is not None and got.rwds_high is not None and ref.rwds_high != got.rwds_high:
            out.append(Mismatch(i, "rwds_high", int(ref.rwds_high), int(got.rwds_high)))
    return out


def apply_hyperram_latency(params: HyperRAMParams, latency_ck: int) -> HyperRAMParams:
    """Program CR0[7:4] to the code that selects ``latency_ck``."""
    code = {5: 0x0, 6: 0x1, 7: 0x2, 3: 0xE, 4: 0xF}[latency_ck]
    cr0 = (params.cr0_reset & ~(0xF << 4)) | (code << 4)
    return replace(params, cr0_reset=cr0)


def apply_rpc_cl(params: RpcDramParams, rl_ck: int) -> RpcDramParams:
    """RL = CL + AL, AL is fixed at 1, so CL = RL - 1."""
    if rl_ck <= params.al:
        raise ValueError("RL must be greater than AL")
    return replace(params, cl=rl_ck - params.al)


def collect_hyperram(dev: HyperRAMDevice) -> list[Observation]:
    obs = []
    prev = None
    for txn in dev.history:
        if txn.space != "mem":
            prev = txn.done
            continue
        obs.append(Observation.from_hyper(txn, prev))
        prev = txn.done
    return obs
