# Existing FireSim / Radiance / HBM infrastructure

Audit date: 2026-11-09. Clones live under `/global/home/tamzid_razzaque/sagar_memory/`. None of these checkouts is the Chipyard tree that last ran on the FPGA host, and the FireSim checkout is ahead of the Chipyard gitlink. `qp_accelerator` was not modified.

## Checkouts

| Tree | Remote | Branch | Commit | What was initialized |
|---|---|---|---|---|
| `firesim` | `tamzidrazzaque/firesim` | `investigation/hbm2-fixed-work` | `8ee723921fc695874e53fc303cc4293df3f2eba9` | Sources plus `sim/cde` `2bcaeae2`, `sim/diplomacy` `a042ff6d`, `sim/berkeley-hardfloat` `26f00d00`, `sim/rocket-chip` `1b9f43352`. Platform FPGA submodules were left uninitialized. |
| `chipyard` | `tamzidrazzaque/chipyard` | `investigation/hbm2-u250-handoff-20261022` | `c2ba24424ce8b1a448d9502f44c17e009dbf2050` | This commit only. Submodules were not checked out. |
| `radiance` | `tamzidrazzaque/radiance` | `investigation/hbm2-u250-dependency-20261022` | `bd6c4b7af8fc90b939061862baa35c2f200899cd` | This commit only. |
| `radiance-kernels` | `tamzidrazzaque/radiance-kernels` | `hbm-gemm-e2e` | `e7dfda4425a018d1a10ce9dc070cda8f358bc265` | This commit only. |

FireSim `8ee72392` (2026-11-08, "Add an HBM4-8000 timing table beside the HBM2 tables") is the latest HBM branch tip. The Chipyard handoff's `sims/firesim` gitlink is `097593341ca1b249b4f92d455d982dcbd668f68d`. Its `generators/radiance` gitlink is `bd6c4b7a`, matching the Radiance clone. `chipyard/investigation/README.md` in that same commit still names FireSim `590ebc4e7e1061a7b96bb333b7c692701a791bac`. The gitlink is the pin that a submodule update would use. The prose in that README is older than the gitlink.

The new technology-spec model is an uncommitted change on top of FireSim `8ee72392`. It is not in the Chipyard handoff.

## Memory-model code

FASED timing models are selected by `firesim.configs.MemModelKey` in `firesim/sim/midas/src/main/scala/configs/FASEDTargetConfigs.scala`. `FASEDMemoryTimingModel` calls `cfg.elaborate()` and attaches the host-DRAM functional memory behind the timing model (`firesim/sim/midas/src/main/scala/midas/models/dram/FASEDMemoryTimingModel.scala`).

| Model | Source | What it times |
|---|---|---|
| Latency pipe | `LatencyBandwidthPipe.scala` | Programmable read and write latency. Despite the class name, it has no separate bandwidth limit. Defaults are 30 target cycles. |
| Bank conflict | `BankConflictModel.scala` | Per-bank queues. |
| DDR3 FCFS | `FIFOMASModel.scala` | FIFO command schedule over the DDR3 bank tracker. |
| DDR3 FR-FCFS | `FRFCFSModel.scala`, `DramCommon.scala` | First-ready FR-FCFS, ACT/PRE/CAS, rank refresh. Runtime example: `sim/custom-runtime-configs/ddr3-FRFCFS-8G-4R-2133-OP-5bridge.conf`. |
| HBM | `HBMModel.scala` | Independent channels. Each channel has pseudo-channels, bank groups, banks, FR-FCFS, REFab/REFSB, and a completion pipe. |

There is no DDR4 or DDR5 FASED timing model. The only DDR4 hit in this FireSim tree is a board-port note in `platforms/corigine_xb10/PORTING.md`. No HyperRAM or RPC DRAM model is in these checkouts.

### HBM2 timing and organization

`HBMModel.scala` is still the HBM2 (JESD235) state machine. Speed tables in `HBMTimingTables` are controller-clock counts:

- `hbm2_2400`, `hbm2_2000`, `hbm2_1600`
- `pare`, currently an alias of `hbm2_2400`
- `hbm4_8000`, added in `8ee72392`, from printed JESD270-4A values plus documented fills from HBM2-2000 nanoseconds and Table 99. `tBL` and `tCMD` are the existing model's burst and command slots.

`HBM4FRFCFS16HiQuadChannel` only changes organization: 8 bank groups, 8 banks per group, 4 channels. `HBM2FRFCFS8HiQuadChannel` is the 8-high, 32-bank organization with one stack-ID bit and a `tCCDR` register. Neither config replaces the HBM2 command path with an HBM4 bus.

Platform classes used by the existing study:

- `HBM2FRFCFS16GBDualPC`: one channel, two pseudo-channels, 16 banks per pseudo-channel, 32/32 read/write entries.
- `HBM2FRFCFS16GBQuadChannel`: four channels inside one `HBMModel`.

Checked-in runtime cards include `sim/custom-runtime-configs/hbm2-FRFCFS-2000-OP-REFSB-5bridge.conf` and the 2400 REFab/REFSB single- and four-channel cards. A five-bridge file programs five FASED instances. The HBM validation README says an unsuffixed template now fails closed; bridge index suffixes are required.

### What one HBM port is

The HBM model consumes timing counts on the target clock. `chipyard/investigation/README.md` records that `WithFireSimConfigTweaks` drives the memory bus at 1 GHz, while the HBM2-2400 table is counted at 0.833 ns. Using those counts on a 1 ns tick stretches modeled time by about 1.20x. The same note says `WithEdgeDataBits(64)` is an 8-byte beat in the source config.

A FASED AXI port's delivered bytes per target cycle are therefore not the HBM stack's pin bandwidth. The fixed-read diagnostic below is the evidence for that.

## Radiance connection

`radiance/chipyard/RadianceRegionMem.scala` (`WithRadianceRegionMemPunchthrough`) exports one AXI4 memory port per Radiance region. The harness receives the whole `ExtMem` range for the backing image. Per-region timing is selected by the FASED bridge on that port.

`chipyard/generators/firechip/chip/src/main/scala/TargetConfigs.scala` instantiates the FireSim Radiance targets, including:

- `FireSimE4M3MxGemminiRadianceConfig` and the two- and four-cluster variants
- `FireSimE4M3MxGemminiHBMRadianceConfig` and `FireSimE4M3MxGemminiTwoClusterHBMRadianceConfig`
- `FireSimE4M3MxGemminiTwoClusterHBMHighDepthRadianceConfig`, which raises L0/L1 in-flight and MSHR counts on the two-cluster HBM target

`chipyard/investigation/README.md` states the topology that those HBM configs use: one 256 KiB host L2 slice plus four 64 KiB GPU L2 slices, five region AXI ports, GPU lines hashed across the four GPU regions. The ordinary target is one memory channel behind a shared 512 KiB L2. Those are different cache designs. A DDR-versus-HBM comparison that also changes the L2 is not a memory-model-only comparison.

In this project one SM is one Radiance cluster, and a cluster has two Muon cores. The two-SM target is four Muon cores. Source for that naming is `chipyard/investigation/workloads.md`.

## Validation already in the HBM branch

`firesim/sim/scripts/hbm-validation/README.md` describes the Ramulator 2.1 legality flow. Pinned Ramulator commit recorded there: `b30320bc9385b708e86b67ebb9f48858cc66d798`. The check replays FASED command traces into Ramulator's HBM2 device. It checks that FASED did not issue a command early. It does not require the two schedulers to match cycle for cycle.

The same directory holds:

- `examples/radiance-memperf-reqtrace-sample.csv`, 5000 HBMREQ rows from a Radiance MemPerf run
- `examples/radiance-memperf-segments.txt`, segment statistics for a 613,255-request, 24M-cycle run that the README reports as 0 Ramulator violations

`sim/midas/src/test/scala/midas/HBMModelSpec.scala` elaborates the HBM and DDR3 FR-FCFS models and checks the HBM2 and HBM4-8000 tables. That spec was not re-run in this session. The new `TechSpecMemorySpec` is the spec this session added.

## Results already measured, and what they are

These numbers are copied from the Chipyard investigation notes. They were not reproduced on this machine. No FPGA was programmed here.

From `chipyard/investigation/hbm-fixed-work-diagnostic-2026-10-21.md`, host Verilator, three identical repeats, 32,768 sequential 32-byte reads, equal port counts. Effective GB/s assumes a 1 GHz target tick:

| Model / ports | Target cycles | GB/s at 1 GHz | Versus the matching DDR run |
|---|---:|---:|---:|
| DDR3-2133 / 1 | 142,897 | 7.338 | baseline |
| HBM2-2000 / 1 | 145,354 | 7.214 | 1.719% more cycles |
| HBM2-2400 counts on a 1 GHz tick / 1 | 145,528 | 7.205 | 1.841% more cycles |
| DDR3-2133 / 4 | 35,696 | 29.375 | baseline |
| HBM2-2000 / 4 | 36,331 | 28.862 | 1.779% more cycles |

One 8-byte FASED port is the limiter. HBM2 is not faster than DDR3 on this sequential probe. A non-physical `tREFI=30000` run made HBM2-2000 faster than DDR, which the note uses as evidence that refresh, not the completion backend, causes most of the valid-profile gap. Sequential REFSB was much slower (246,343 one-port cycles). The same addresses in bank-interleaved order made REFSB faster than REFab (131,299 one-port cycles) with zero Ramulator violations on that trace.

From `chipyard/investigation/README.md`, host-Verilator two-SM STREAM Copy smokes, same pinned ELF. These prove the target boots and the profiles load. The kernel is tiny. Host wall time is not XB10 performance.

| Profile | Total target cycles | Kernel cycles |
|---|---:|---:|
| HBM2-2400 | 395,266 | 13,670 |
| HBM2-2000 | 392,194 | 12,682 |
| DDR3-2133 | 386,050 | 11,538 |

`chipyard/investigation/workloads.md` records the native STREAM and Spatter matrix (Copy/Scale/Add/Triad and Spatter 0-4) and the ELF hashes. Those ELFs are not in the `hbm-gemm-e2e` kernel clone used here. That clone contains `soc/muon.elf` only. No new ELF was built and no workload was launched.

## Clocks, cycles, and bandwidth, kept separate

- **Memory-model latency** is a count of target cycles inside the FASED timing model (tCAS, the latency pipe's `readLatency`, or the new model's release formula).
- **Simulated target cycles** are the cycles reported by the FireSim target, including the core, caches, and every bridge.
- **Physical DRAM time** is the JEDEC nanosecond value. Dividing by the real tCK produces the table in `HBMTimingTables`. Applying that table on a 1 ns model tick is a different physical time than HBM2-2400.
- **FPGA host clock** is the clock of the emulator. It is not the 1 GHz target tick. This session did not run on an FPGA, so no host-clock measurement was taken.
- **GPU cycles** in the STREAM smoke are the kernel-cycle column above, not the total target-cycle column.
- **AXI / backing-memory throughput** is what the 8-byte FASED port and the host DRAM functional model actually move. The fixed-read table is that quantity. It is not an HBM stack's advertised pin bandwidth.

## What is already solved, and what is missing

Solved in the existing branch: an HBM2 FR-FCFS model with multi-channel organization, HBM2-1600/2000/2400 tables, an HBM4-8000 table and 16-high organization on that same machine, DDR3 FR-FCFS, runtime profiles for five bridges, Ramulator legality checks, and Radiance region ports that can host one FASED model per region.

Missing for the Sagar direction: a non-DRAM technology card, endurance and retention accounting that does not pretend to be DRAM refresh, a closed-loop run in which only that card changes, and any calibrated FeFET or other emerging-device numbers. DDR5 is also absent. The Chipyard handoff does not yet point at FireSim `8ee72392`, so the HBM4 table and the new model are not what the last handoff document describes.
