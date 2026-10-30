"""Compare a Verilated FASED trace with the Python timing model.

Cycles in the Verilator log are the Chisel ``tCycle`` counter, which keeps
running through reset and host startup. Comparisons use the delta from the
first accepted request, not the absolute counter.

The Chisel model does not store bytes. Data checks stay on the Python device.
The AXI fuzzer's ``error`` output is hard-wired to 0, so a fuzzer exit code
does not prove that read data matched.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Obs:
    cycle: int
    is_write: bool
    addr: int
    xid: int
    length: int  # AXI len, beats minus one, or a byte count if from Python
    extra: int = 0


def parse_trace(text: str, kind: str) -> list[Obs]:
    out = []
    prefix = "HYPERREQ" if kind == "hyperram" else "RPCREQ"
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith(prefix + ","):
            continue
        p = [x.strip() for x in line.split(",")]
        if kind == "hyperram":
            # cycle, isWrite, addr, id, len_or_bytes, latency_or_n, extra, row
            out.append(Obs(int(p[1]), bool(int(p[2])), int(p[3], 16), int(p[4]), int(p[5]), int(p[7]) if len(p) > 7 else 0))
        else:
            out.append(Obs(int(p[1]), bool(int(p[2])), int(p[3], 16), int(p[4]), int(p[5])))
    return out


def chisel_hyper_starts(reqs: list[Obs], *, beat_bytes: int = 8, from_fuzzer: bool = True) -> list[int]:
    """Inter-accept times of the Chisel HyperRAM model, fixed latency 14.

    Fuzzer traces carry AXI ``len``. Python traces carry a byte count in the
    same field. ``from_fuzzer`` selects the decoding.
    """
    cs_rise = 0
    have = False
    last_write = False
    starts = []
    for req in reqs:
        nbytes = (req.length + 1) * beat_bytes if from_fuzzer else req.length
        # One chip-select unless tCSM forces a split. 8..64 B fits in 4 us.
        data_ck = (nbytes + 1) // 2
        gap = 0
        if have:
            gap = 7 if (not last_write and req.is_write) else 2
        start = cs_rise + gap
        starts.append(start)
        cs_rise = start + 3 + 14 + data_ck
        have = True
        last_write = req.is_write
    return starts


def relative(cycles: list[int]) -> list[int]:
    if not cycles:
        return []
    base = cycles[0]
    return [c - base for c in cycles]


@dataclass
class Mismatch:
    index: int
    field: str
    python_ck: int
    verilated_ck: int

    def __str__(self) -> str:
        return f"[{self.index}] {self.field}: python {self.python_ck} verilated {self.verilated_ck}"


def compare_starts(predicted: list[int], observed: list[Obs]) -> list[Mismatch]:
    rel_p = relative(predicted)
    rel_o = relative([o.cycle for o in observed])
    n = min(len(rel_p), len(rel_o))
    bad = []
    if len(rel_p) != len(rel_o):
        bad.append(Mismatch(-1, "count", len(rel_p), len(rel_o)))
    for i in range(n):
        if rel_p[i] != rel_o[i]:
            bad.append(Mismatch(i, "accept_delta", rel_p[i], rel_o[i]))
    return bad
