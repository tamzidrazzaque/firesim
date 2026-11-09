# TechSpec metasim validation

Date: 2026-11-09. Host: `armada.eecs.berkeley.edu`.

The isolated Chisel elaboration in `TechSpecMemorySpec` does not attach the FASED control-register file. The first Golden Gate run failed there: `Widget.genAndAttachReg` requires every MMIO field to be at most `CtrlNastiKey.dataBits` (32). The byte and cycle counters were 64 bits. They are now 32-bit fields and wrap at 2^32. After that change, Golden Gate emitted Verilog and Verilator 5.022 linked the simulator.

## Simulator

| Item | Value |
|---|---|
| Binary | `sim/generated-src/f2/f2-fasedtests-AXI4Fuzzer-NT200_DefaultConfig-TechSpecF2TraceConfig/VAXI4Fuzzer` |
| Make | GNU make 4.4.1. The system make is 4.2.1 and rejects the grouped `&:` rules in this tree. |
| C++ | gcc-toolset 12.2.1. The system g++ 8.5 rejects `-std=c++20`. |
| Verilator | 5.022, built locally. The man-page install step failed; the include tree was copied from the build. |
| Target | `AXI4Fuzzer`, `NT200_DefaultConfig`: 200 TileLink transactions, 8-byte beats, checked by `TLRAMModel`. |
| Platform | `TechSpecF2TraceConfig`: illustrative card, `SynthPrints` on. |
| Plusargs | `+mm_useHardwareDefaultRuntimeSettings_0` plus the swept overrides and `+mm_traceEnable_0=1`. |

`TECHSPEC` lines are the timing-model admit, start, and release. They are not the target-visible AXI last beat. That beat is later, after egress and the functional host memory. The pass/fail of the fuzzer is the target-visible path: every read data value checked, and the simulator printed `*** PASSED ***`.

## Rule check

`sim/scripts/emerging-memory/check_techspec_trace.py` recomputes, from each admit:

```
occupancy = max(programmedService, axiLen + 1)
start     = max(admitCycle, nextService)
release   = start + latency - 1
```

A read admitted on the same cycle as a write is ordered first. Service windows must not overlap.

Seven runs, 200 admits each, **zero rule errors**:

| Run | Passed target cycles | Traffic cycles after first admit | Checker |
|---|---:|---:|---|
| latency 30, service 1, outstanding 32 | 525,439 | 1,050 | 0 errors |
| latency 30, service 1, outstanding 8 | 525,518 | 1,129 | 0 errors |
| latency 30, service 1, outstanding 4 | 526,009 | 1,620 | 0 errors |
| latency 200, service 1, outstanding 32 | 525,911 | 1,522 | 0 errors |
| latency 200, service 1, outstanding 4 | 534,115 | 9,726 | 0 errors |
| latency 1000, service 1, outstanding 32 | 530,727 | 6,338 | 0 errors |
| latency 30, service 32, outstanding 32 | 530,848 | 6,459 | 0 errors |

The first admit is target cycle 524,389 in every TechSpec run. The ~524k cycles before that are reset and bridge startup, common to the sweeps. Traffic cycles are `passed cycle - 524389`.

On the latency-30, service-1, outstanding-32 run the model counted 190 reads, 10 writes, 483 read bytes, 30 write bytes, and 227 issuer-busy cycles. `rrespError` and `brespError` are 0. Read-outstanding occupancy stayed at or below 8; the 32-entry cap was not full.

Logs and per-run `*.check.json` files are in `research/emerging_memory/results/metasim/`.
