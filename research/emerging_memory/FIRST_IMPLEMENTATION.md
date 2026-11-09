# First implementation

The first slice is a byte-addressable technology-spec timing model next to the existing HBM and DDR3 models. It is the smallest model that can carry a non-DRAM card, including endurance and retention accounting, and that can be checked without an FPGA.

## Why this slice, and not the others

DDR5 would be another DRAM table on the FR-FCFS machine. The branch already grew that way yesterday: `hbm4_8000` is a table on `HBMModel`, and `HBM4FRFCFS16HiQuadChannel` is an organization change. A second DRAM grade does not create a place to put endurance or a non-DRAM address model.

An endurance wrapper around HBM would edit the model Ramulator is used to check. The HBM counters and refresh behavior would have to be re-proven. The new counters sit on a new module instead.

A 3D NAND page model needs a page/block address map and program/erase timing we do not have a calibrated source for. Putting that behind an AXI byte port would claim the GPU can use NAND as DRAM. Sagar asked for technology models without prescribing that hookup.

The technology-spec model is a `TimingModel` with a shared issuer, separate read and write latencies, a beat-aware occupancy, and reliability counters that do not change data. A later DDR5 table can still be added as DRAM. A later NAND model can still be added as its own key. A calibrated FeFET card, when one exists, drops into this key if the cell is used as a byte-addressable memory. If it is used as a string, it does not.

## Files

| Path | Role |
|---|---|
| `sim/midas/src/main/scala/midas/models/dram/TechSpecMemory.scala` | Chisel timing model |
| `sim/midas/src/main/scala/configs/FASEDTargetConfigs.scala` | `WithTechSpecMemory`, `TechSpecByteNVM`, `TechSpecByteNVMTrace` |
| `sim/src/main/scala/fasedtests/Config.scala` | `TechSpecF2Config` |
| `sim/src/main/scala/midasexamples/Config.scala` | `PointerChaserTechSpec` |
| `sim/midas/src/test/scala/midas/TechSpecMemorySpec.scala` | Elaboration and config identity |
| `sim/custom-runtime-configs/techspec-illustrative-byte-nvm.conf` | One-bridge runtime card |
| `sim/scripts/emerging-memory/techspec.py` | Cycle-accurate reference of the timing-model rules |
| `sim/scripts/emerging-memory/test_techspec.py` | Directed tests of those rules |
| `sim/scripts/emerging-memory/replay_trace.py` | Open-loop replay of the MemPerf sample |
| `sim/scripts/emerging-memory/specs/illustrative_byte_addressable_nvm.json` | Versioned card |

`HBMModel.scala` and the HBM platform classes were not edited.

## Counters

On the timing-model register block:

- `admittedReads`, `admittedWrites`
- `deviceReadBytes`, `deviceWriteBytes`, `logicalWriteBytes` (the last two match)
- `issuerBusyCycles`
- `enduranceExceeded`
- `retentionFreshReads`, `retentionStaleReads`, `retentionUnknownReads`

The existing FASED transaction and beat counters remain, because `TechSpecByteNVM` sets `beatCounters`. `totalWrites` still counts AW acceptance. `admittedWrites` counts the cycle when AW and the last W beat have both arrived. Those differ if the address arrives early.

Optional trace, only if elaborated with `requestTrace` and `traceEnable=1`:

```
TECHSPEC,<cycle>,<isWrite>,<addr>,<id>,<len>,<size>,<start>,<release>
```

## Reproduce the reference

From `firesim/sim/scripts/emerging-memory`, with the FireSim tree as the current directory's repo:

```bash
python3 -m unittest test_techspec.py
python3 replay_trace.py
```

The replay writes `research/emerging_memory/results/techspec_sample_sensitivity.json` and, if matplotlib imports, `techspec_sample_sensitivity.png`.

Chisel elaboration, from `firesim/sim`, with JDK 17. This machine's default `java` is 8, which this build does not use. The JDK and sbt used here are under `/global/home/tamzid_razzaque/sagar_memory/toolchains/`.

```bash
export JAVA_HOME=/global/home/tamzid_razzaque/sagar_memory/toolchains/jdk-17
export PATH="$JAVA_HOME/bin:/global/home/tamzid_razzaque/sagar_memory/toolchains/sbt/bin:$PATH"
cd /global/home/tamzid_razzaque/sagar_memory/firesim/sim
sbt -batch "midas/testOnly goldengate.tests.TechSpecMemorySpec"
```

A metasim of `TechSpecF2Config` was not run. An FPGA image was not built.
