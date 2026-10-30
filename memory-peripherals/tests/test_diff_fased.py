"""Differential checks against the Verilated FASED traces.

The absolute tCycle in those logs includes reset. Only deltas are compared.
"""

from pathlib import Path

from memperiph.diffharness import chisel_hyper_starts, compare_starts, parse_trace

ROOT = Path(__file__).resolve().parents[1]
HYPER = ROOT / "results" / "logs" / "hyperram-fuzzer-run.log"
RPC = ROOT / "results" / "logs" / "rpc-fuzzer-run.log"


def test_verilated_hyperram_gaps_match_the_chisel_formula():
    text = HYPER.read_text(errors="replace")
    obs = parse_trace(text, "hyperram")
    assert len(obs) == 10000
    # Fixed-latency column is 14 on every accepted request.
    assert all(o.extra == 1 for o in obs)
    # Spot-check the read-to-write and write-to-read gaps on the first three.
    assert obs[1].cycle - obs[0].cycle == 28  # 3+14+4 data + tRWR 7
    assert obs[2].cycle - obs[1].cycle == 23  # 3+14+4 + tCSHI 2
    predicted = chisel_hyper_starts(obs, from_fuzzer=True)
    mismatches = compare_starts(predicted, obs)
    report = ROOT / "results" / "differential" / "hyperram.txt"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        f"requests {len(obs)}\nmismatches {len(mismatches)}\n"
        + "\n".join(str(m) for m in mismatches[:40])
        + "\n"
    )
    assert mismatches == [], report.read_text()[:500]


def test_verilated_rpc_trace_has_ten_thousand_commands_and_a_row_decode():
    text = RPC.read_text(errors="replace")
    obs = parse_trace(text, "rpc")
    assert len(obs) == 10000
    # 0x212e40 -> row addr[22:11] = 0x425. Bank stays 0: the fuzzer has 22 bits.
    hit = [o for o in obs if o.addr == 0x212E40]
    assert hit, "expected the fuzzer to touch 0x212e40"
    # The row is not in Obs; re-parse one line.
    for line in text.splitlines():
        if line.strip().startswith("RPCREQ") and "212e40" in line.lower().replace(" ", ""):
            fields = [x.strip() for x in line.split(",")]
            assert int(fields[6]) == 0
            assert int(fields[7], 16) == 0x425
            break
    else:
        raise AssertionError("row decode line missing")
