# HBM2 FASED Model — Recovery & Validation Report

This report documents the reconstruction and re-validation of the HBM2
timing-model work on a fresh VM, after the loss of the previous development
machine. Base branch: `hbm-modeling` (`013ec3907`, "Add HBM2 pseudo-channel
timing model to FASED").

## Environment

| Component | Version |
| --------- | ------- |
| OS | Ubuntu 24.04.4 LTS (kernel 6.8.0-138-generic), x86-64 |
| C/C++ toolchain | g++ 13.3.0 (system; conda verilator's bundled gcc 16 is too new for this tree and is overridden with `CXX=g++ CC=gcc`) |
| Verilator | 5.022 (conda-forge, same version FireSim's conda lockfile pins) |
| Java / sbt | OpenJDK 20.0.2 (conda-forge), sbt via the repo's `sbt-launch.jar` |
| CMake | 3.28.3 |
| Python | 3.12.3 (venv for Ramulator) |
| Simulator | Verilator metasimulation (FireSim "MIDAS-level" flow, `PLATFORM=f2`) |
| Ramulator 2.1 | commit `b30320bc9385b708e86b67ebb9f48858cc66d798` (pinned, built outside the FireSim tree with python bindings) |
| FireSim base | `hbm-modeling` @ `013ec3907` |

Notes for this specific VM: no sudo and no writable `$HOME`; all tooling
lives under `/scratch` (miniforge env `fsim`, `gh` prebuilt binary), and sbt
is pointed away from `$HOME` with `-Duser.home` / `-Dsbt.*` properties.

## What was already on `hbm-modeling`

- `sim/midas/src/main/scala/midas/models/dram/HBMModel.scala`: the complete
  HBM2 pseudo-channel model — organization (2 PCs x 4 bank groups x 4 banks),
  split row/column command buses with 2-cycle ACT row-bus occupancy,
  hierarchical bank / bank-group / pseudo-channel timing trackers, FR-FCFS
  scheduling over a collapsing reference buffer, REFab + REFSB refresh with
  runtime `perBankRefresh` selection, hardware assertions on every command
  class, and HBM2-2400/2000/1600 runtime timing tables.
- `cmd_refsb` in `DRAMMasEnums` + `CommandBusMonitor` refsb printf.
- Configs: `WithHBM2FRFCFS`, `HBM2FRFCFS16GBDualPC(LLC4MB)`, `HBMF2Config`
  (AXI4Fuzzer platform), `PointerChaserHBM`.
- `HBMModelSpec` (3 tests: DDR3-FRFCFS control elaboration, HBMModel
  elaboration + Verilog lowering, timing-table completeness).

## What had to be reconstructed

1. **16-bit HBM timing path (`hbmTimingBits = 16`)** — the branch still used
   the DDR model's `maxDRAMTimingBits = 7` (and `tRFCBits = 10`) for every
   HBM timing register, DownCounter, the tFAW queue, and the tCycle input
   used for tFAW bookkeeping. All widened to a dedicated
   `HasHBMTimingConstants.hbmTimingBits = 16`; the HBM backend was widened to
   16-bit latencies (`DRAMBackendKey(4, 4, 16)`) so `tCAS + backendLatency`
   cannot truncate in the `DynamicLatencyPipe`.
2. **JESD235 two-frame-ACT timing semantics** — ACT occupies the row bus for
   2 CK and the DRAM registers it on its *second* frame. The branch measured
   all ACT-relative timings from the first frame, which cross-validation
   against Ramulator immediately flagged (~934 timing violations in the first
   trace: every row-miss CAS issued at ACT+tRCD instead of ACT+tRCD+1, etc.).
   The bank tracker now programs tRCDRD/tRCDWR/tRAS/tRC un-decremented, so
   RD/WR/PRE/REF become legal at ACT + t + 1 while ACT-to-ACT spacings
   (tRRD/tFAW, second-frame to second-frame, offsets cancel) are unchanged.
   After the fix all traces replay violation-free (see below).
3. **Ramulator reference environment** — rebuilt outside the FireSim tree at
   the pinned commit, with its python bindings and pytest suite.
4. **Trace tooling + cross-validation** — `sim/scripts/hbm-validation/`
   (trace parser, Ramulator replay checker, end-to-end runner). Not present
   on the branch at all.
5. **HBM runtime configuration fixtures** —
   `sim/custom-runtime-configs/hbm2-FRFCFS-2400-{OP-REFab,OP-REFSB,CP-REFab}.conf`
   containing the complete HBM2-2400 register set.
6. **Small infrastructure fixes** — `make conf` invoked
   `RuntimeConfigGeneratorMain` without the required output-name flag (fixed
   to pass `-ggrc`; note the stage itself still has pre-existing upstream
   bitrot, see Known limitations); `generate_memory_init.py` gained an
   optional `--seed` so PointerChaser runs are reproducible; a directed
   row-conflict fuzzer config (`FuzzMaskSingleBank`) was added.

## HBM architecture (as recovered)

```
AXI4 -> UnifiedFIFOXactionScheduler -> HBM address decode (PC / BG / bank / row,
runtime-programmable offsets+masks) -> collapsing FR-FCFS reference buffer
  -> column arbiter: one legal RD/WR per cycle (first-ready, oldest-first)
  -> row path:      one legal row cmd per cycle, priority
                    REFab > REFSB > refresh-prep PRE > ACT > PRE
  -> hierarchical trackers:
       bank:        open row, next-legal ACT/PRE/RD/WR
       bank group:  tCCDL / tRRDL / tWTRL (long timings)
       pseudo-ch.:  tCCDS / tRRDS / tWTRS, RD<->WR turnaround, tFAW queue,
                    refresh state (REFab or per-bank round-robin REFSB)
       shared:      row bus busy 1 extra cycle after ACT (2-frame ACT)
  -> DRAMBackend (16-bit dynamic latency pipes) -> AXI4 R/B channels
```

Row and column commands may issue in the same modeled CK; an assertion
forbids same-bank row+column commands in one cycle, and every tracker
asserts a command is legal when it is issued.

FR-FCFS specifics: column path prioritizes ready (row-hit) references
oldest-first; the row path only ACTs for references that are not ready and
only PREs when no pending reference still hits the open row (`mayPRE`).
There is no read/write batching or write-drain mode in this model: reads and
writes arbitrate in a single first-ready stream, and writes are acknowledged
at issue (`writeLatency = 1`), reads complete after `tCAS + backendLatency`.

## HBM2 timing configuration (FASED vs pinned Ramulator)

FASED `HBMTimingTables.hbm2_2400` vs Ramulator `HBM2_2400Mbps` preset +
`HBM2_8Gb` org (secondary timings resolved by Ramulator from JESD235 ns
values at tCK = 833 ps). Every field matches value-for-value:

| Timing | FASED HBM2-2400 | Ramulator HBM2-2400 (`HBM2_2400Mbps`/`HBM2_8Gb`) | Match |
| ------ | --------------- | ------------------------------------------------ | ----- |
| tCK | 833 ps | `tCK_ps` = 833 | yes |
| Read latency / nCL | tCAS = 17 (read latency = tCAS + backendLatency) | nCL = 17 (`read_latency` = nCL + nBL = 19) | yes (nCL) |
| nCWL | tCWD = 6 | nCWL = 6 | yes |
| nBL | tBL = 2 | nBL = 2 | yes |
| tRCD_RD | tRCDRD = 17 | nRCDRD = 17 | yes |
| tRCD_WR | tRCDWR = 14 | nRCDWR = 14 | yes |
| tRC | tRC = 57 | nRC = 57 | yes |
| tRP | tRP = 17 | nRP = 17 | yes |
| tRAS | tRAS = 40 | nRAS = 40 | yes |
| tRTP | tRTP = 6 | nRTPL = 6 | yes |
| tWR | tWR = 19 | nWR = 19 | yes |
| tCCDS / tCCDL | 2 / 4 | 2 / 4 | yes |
| tRRDS / tRRDL | 5 / 5 | 5 / 5 | yes |
| tFAW | 19 | nFAW = 19 | yes |
| tWTRS / tWTRL | 8 / 10 | 8 / 10 | yes |
| tREFI | 4682 | nREFI = 4682 | yes |
| tRFC (all-bank) | 421 | nRFC = 421 (8 Gb) | yes |
| single/per-bank refresh timing | tRFCSB = 193, tRREFD = 10, interval tREFI/16 per PC (= 292/PC, ~146/channel) | nRFCpb = 193, nRREFD = 10, nREFIpb = 147 (channel-wide/32 banks) | yes (same rate, FASED schedules per PC) |
| RD->WR turnaround | nCL + nBL + 2 - nCWL = 15 CK | same expression = 15 CK | yes |

Ramulator is the independent HBM2-2400 reference. It is **not** a PARE
reference; the `PARE` entry in `HBMTimingTables` remains an explicit
placeholder aliasing HBM2-2400 until the real PARE table is provided.

## Test commands

All from `sim/` with the metasim environment sourced
(`FIRESIM_ENV_SOURCED=1`, verilator 5.022 on PATH; on this VM additionally
`CXX=g++ CC=gcc`):

```bash
# 1. Unit tests
sbt "midas/testOnly goldengate.tests.HBMModelSpec"

# 2-5. Full metasim + trace + Ramulator validation pipeline
export RAMULATOR2_DIR=/path/to/ramulator2   # pinned b30320bc938, built + venv
./scripts/hbm-validation/run_hbm_validation.sh <outdir>

# Ramulator baseline tests (from the ramulator2 checkout)
.venv/bin/python -m pytest tests/ -q
```

## Test results (measured on this VM)

| Test | Result |
| ---- | ------ |
| Unit tests (elaboration + timing tables), `HBMModelSpec` | **3/3 passed** |
| PointerChaser metasim (all-bank refresh) | **Passed**, 2489 cycles (seeded list, seed=0; see note) |
| AXI4 fuzzer metasim (all-bank refresh) | **Passed**, 1000 transactions (852 RD + 148 WR), 228 REFab, no assertion failures |
| AXI4 fuzzer metasim (single-bank refresh) | **Passed**, **3654 REFSB events** (matches previous result exactly), 0 REFab, no assertion failures |
| Command trace check (FASED + Ramulator) | **0 violations across 6 traces** (11,324 commands replayed) |
| Ramulator baseline test suite (pinned commit) | **257 passed, 0 failed, 0 skipped** (previous notes said 246 passed; the pinned tree yields 257 collectible tests in this environment — all pass) |

Per-trace Ramulator legality results:

| Trace | Commands checked | Violations |
| ----- | ---------------- | ---------- |
| t1 fuzzer REFab | 2283 (540 ACT / 852 RD / 148 WR / 515 PRE / 228 REFab) | 0 |
| t2 fuzzer REFSB | 5691 (incl. 3654 REFpb) | 0 |
| t3 fuzzer closed-page (RDA/WRA) | 1839 | 0 |
| t4 fuzzer row-hit (mask 0x3FFF) | 1270 (29 ACT for 1000 CAS) | 0 |
| t5 fuzzer row-conflict (mask 0x3F83FF) | 2121 (443 ACT / 442 PRE) | 0 |
| t6 PointerChaser | 120 | 0 |

### PointerChaser cycle-count note (2489 vs historical 2440)

The historical 2440 is not bit-reproducible, for two understood reasons:

1. `generate_memory_init.py` builds the linked list with an *unseeded*
   `random.sample`, so the lost VM's list (and hence its row-hit/conflict
   pattern) cannot be regenerated. Re-running with fresh lists gives cycle
   counts in the same ~2.4-2.5k range (e.g. 2457 on the pre-fix model with
   one random list). The generator now accepts `--seed`; the validation
   pipeline uses seed 0, which gives a stable 2489.
2. The reconstructed two-frame-ACT correction adds one cycle per row-miss
   activation on PointerChaser's serial dependence chain (49 ACTs in the
   seeded run), which Ramulator confirms is the JESD235-correct behavior;
   without it, the trace check reports hundreds of tRCD/tRAS violations.

## FASED vs Ramulator validation

Methodology: every command issued by the FASED model (both command buses,
extracted from the CommandBusMonitor printfs in the metasim logs) is
replayed, at its issue cycle, into pinned Ramulator's HBM2 C++ device model
via Ramulator's own test harness. A command Ramulator considers not-ready
(bank-state prerequisite or any JESD235 timing constraint) at that cycle is
a violation. This is a timing-*legality* comparison — it does **not** claim
cycle-identical scheduling between the two controllers. FASED's hardware
assertions were active in all runs. Known conservative-in-FASED differences
(cannot mask violations): REFSB counts toward FASED's tFAW window and REFSB
is spaced from REFSB/ACT by tRREFD, both stricter than Ramulator requires;
PRE->ACT and REF->ACT are measured to the ACT's first frame (Ramulator
permits the first frame one cycle earlier).

Result: **0 violations across all 6 traces** (previous baseline: 0 across 5).

## Known limitations

- The PARE timing table is a placeholder aliasing HBM2-2400.
- `midas.stage.RuntimeConfigGeneratorMain` (`make conf`) has pre-existing
  upstream bitrot beyond the flag fix made here: it constructs a
  `LazyModule` outside a Chisel builder context and crashes for any model
  (DDR3 included). The complete HBM register list is instead maintained in
  `sim/custom-runtime-configs/hbm2-*.conf` and verified end-to-end: the
  FASED driver errors at startup if any writable register is not covered by
  the supplied `+mm_*` args, so a traversal regression cannot pass CI runs
  that use these confs.
- The trace checker replays commands into Ramulator's device model; on a
  (hypothetical) violation it reports and skips the command, so subsequent
  same-bank checks in that trace may be perturbed — exact counts past the
  first violation are advisory. All current traces are violation-free.
- One-cycle-conservative choices (documented in `HBMModel.scala`): same-bank
  ACT->ACT honors tRC+1 (so the shared bank-ACT gate is exact for
  ACT->REFab/REFSB), and PRE/REF->ACT do not exploit the second-frame ACT
  allowance.
- Writes are acknowledged at issue (single-cycle backend write latency), as
  in the other FASED MAS models.

## Remaining integration work (future, intentionally not started)

- Drop in the real PARE timing table and controller-policy differences
  (Andre / PARE / Radiance integration).
- Multi-channel HBM stacks (this model is one channel in PC mode; multiple
  FASED instances give multiple channels).
- Optional: strict cycle-by-cycle co-simulation against a Ramulator
  controller configured to mirror FASED's scheduler policy.
