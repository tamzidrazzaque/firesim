# Closed-loop results

The master is the existing FireSim `AXI4Fuzzer` (`NT200_DefaultConfig`), not Radiance. The same 200-transaction target was rebuilt three times. Only `PLATFORM_CONFIG` changed.

| Platform config | Memory model | Runtime profile | Target cycles | Result |
|---|---|---|---:|---|
| `TechSpecF2TraceConfig` | TechSpec | hardware defaults: latency 30, service 1, outstanding 32 | 525,439 | PASSED |
| `DDRF2Config` | DDR3 FR-FCFS, 8 GB quad-rank class | hardware defaults | 526,009 | PASSED |
| `HBMF2Config` | HBM2 FR-FCFS, one channel, dual pseudo-channel | hardware defaults (HBM2-2400 table) | 526,960 | PASSED |

TechSpec and HBM both counted 190 reads, 10 writes, 217 read beats, and 10 write beats. Response errors were 0. DDR used the same fuzzer configuration and passed; its stats file was overwritten by the HBM run before it was copied, so DDR beat counts are not in the saved CSV. The cycle count is from `ddr3-frfcfs.stderr`.

Against the TechSpec total:

- DDR3 took 570 more target cycles (0.11% of the full run, about half of the 1,050-cycle TechSpec traffic window).
- HBM2 took 1,521 more target cycles (0.29% of the full run).

Those are simulator target cycles of this fuzzer. They are not FPGA host time, not a 1 GHz GPU kernel, and not HBM pin bandwidth. The AXI port is 8 bytes wide. TechSpec moved 513 payload bytes in the latency-30 run (`deviceReadBytes + deviceWriteBytes`), which is 0.49 bytes per cycle of the 1,050-cycle traffic window, far under 8 bytes per cycle.

## What did not run

A Radiance, STREAM, Spatter, GEMM, or LLM workload did not run.

The two-SM ELFs and the Chipyard tree that has already built them are recorded under `/scratch/trazzaque/chipyard` on Harp. `ssh harp.millennium.berkeley.edu` from this machine returned `Permission denied (publickey)`. That tree is not mounted on Armada. There is no local RISC-V toolchain on `PATH`, and this FireSim checkout does not have the Radiance generators initialized. Rebuilding that stack here would be a new Chipyard checkout, not a reuse of the existing run.

Figure: `research/emerging_memory/results/closed_loop_memory_comparison.png`. The bars are target cycles minus 524,000 so the memory-phase difference is visible. The labels are the full totals.
