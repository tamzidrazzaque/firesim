# HBM2 FASED model validation

Tools to validate the FASED HBM2 timing model (`midas.models.HBMModel`)
against [Ramulator 2.1](https://github.com/CMU-SAFARI/ramulator2) as an
independent JESD235 timing reference.

Pinned Ramulator commit: `b30320bc9385b708e86b67ebb9f48858cc66d798`.

## Methodology

1. Verilator metasims of directed workloads are run against the HBM model
   (`HBMF2Config` / `PointerChaserHBM`). The model's two `CommandBusMonitor`s
   print every issued HBM command (ACT / PRE / RD / WR / REFab / REFSB with
   pseudo-channel, bank, row, cycle) into the metasim log.
2. `parse_fased_trace.py` extracts a normalized command trace (CSV).
3. `check_trace_ramulator.py` replays the trace, cycle-stamped, into
   Ramulator's HBM2 device model (`HBM2_2400Mbps` / `HBM2_8Gb`) via its
   nanobind test harness. Every command is first probed; a command Ramulator
   reports as not-ready (state machine or timing) at the cycle FASED issued
   it counts as a violation.

This is a **timing-legality** check, not a cycle-identical-scheduling
comparison: FASED and Ramulator's own controller schedule differently, but a
clean run proves FASED never issues a command earlier than JESD235 permits.
In addition, the model's own hardware assertions (bank / bank-group /
pseudo-channel trackers) are active in every metasim.

## Workloads / traces

| Trace | Workload | What it stresses |
| ----- | -------- | ---------------- |
| t1_fuzzer_refab | AXI4Fuzzer, 1000 xactions, full 22b addresses | bank-group + PC interleave, RD/WR turnaround, REFab |
| t2_fuzzer_refsb | same, `perBankRefresh=1` | REFSB scheduling, tRFCSB / tRREFD |
| t3_fuzzer_closedpage | same, `openPagePolicy=0` | RDA/WRA auto-precharge timing |
| t4_fuzzer_rowhit | fuzzer masked to 0x3FFF (PC0, row 0, all banks) | row hits, tCCDS vs tCCDL |
| t5_fuzzer_rowconflict | fuzzer masked to 0x3F83FF (PC0 bank 0, 128 rows) | row conflicts, tRC / tRAS / tRP / tRCD |
| t6_pointerchaser | PointerChaser (dependent loads, seeded list) | serial latency path end-to-end |

## Running

```bash
# one-time: build ramulator2 at the pinned commit with python bindings,
# and pip install -e it into a venv (see repo README)
export RAMULATOR2_DIR=/path/to/ramulator2
cd sim && ./scripts/hbm-validation/run_hbm_validation.sh /tmp/hbm-validation
```

Individual traces can be checked with:

```bash
./scripts/hbm-validation/parse_fased_trace.py metasim.log -o trace.csv
./scripts/hbm-validation/check_trace_ramulator.py trace.csv --ramulator $RAMULATOR2_DIR
```

## HBM runtime configurations

`sim/custom-runtime-configs/hbm2-FRFCFS-2400-{OP-REFab,OP-REFSB,CP-REFab}.conf`
hold the complete HBM2-2400 register set (every field of
`HBMProgrammableTimings`, the address decode sub-fields, and the policy
bits). Supplying a complete explicit configuration also regression-tests the
`HasProgrammableRegisters` traversal: the FASED driver throws at startup if
any writable register is left uncovered by the supplied `+mm_*` arguments.
