# Validation

Base commit before these edits: FireSim `8ee723921fc695874e53fc303cc4293df3f2eba9`. The model and tests are uncommitted on that commit. Python 3 on this machine ran the reference. JDK is Temurin 17.0.21. sbt is 1.10.1. Matplotlib wrote the sensitivity figure.

## What the Python reference checks

`test_techspec.py` passed 13 tests in one run, and the determinism test runs the same stimulus twice.

| Check | Result |
|---|---|
| Single-beat latency 1 releases on the admit cycle (`start + 1 - 1`) and completes in that cycle because the pipe flows | passed |
| Latency 30 releases at `start + 29` | passed |
| A 4-beat burst with service 1 occupies 4 cycles; the next burst starts 4 cycles later | passed |
| Same-cycle read starts before the write; the overlap checker accepts that schedule | passed |
| AW one cycle before the last W beat admits the write on the second cycle | passed |
| With one outstanding entry, a second read is refused on the completion cycle and admitted the cycle after | passed |
| A sink that is not ready holds the head and the outstanding count | passed |
| Two writes past a one-transfer endurance budget set the flag and keep the same release cycles | passed |
| Retention: age greater than the window is stale; age equal to the window is fresh; a conflicting tag is unknown; a zero window does not classify | passed |
| Two 64-byte addresses in one granule share a set index | passed |
| A hand-written overlap is reported, and a back-to-back legal pair is not | passed |
| `advance_to` matches cycle-by-cycle stepping on a mixed schedule, including issuer-busy counts | passed |
| A second run of one mixed schedule matches the first | passed |

The overlap checker is the intentional-violation test. The model is expected to emit an empty violation list. A schedule with starts at 0 and 2, each of occupancy 4, is reported.

## What the Python reference does not check

It does not drive Chisel. Outstanding counts in Python drop when the timing-model response is accepted. In `TimingModel`, `pendingReads` drops when the target R channel fires its last beat, after the egress unit and the host functional memory. A Python "queue full" cycle is the timing-model boundary. It is not yet a measured AXI-port cycle.

The reference does not contain the HBM or DDR3 command timers. It does not check functional bytes. Those bytes stay in the host backing store, which this session did not simulate.

Address mapping for the retention sample is the shift-and-mask in `retention_index`. There is no bank map to compare to HBM.

## Chisel spec

Command, from `firesim/sim`, JDK Temurin 17.0.21, sbt 1.10.1:

```bash
sbt -batch "midas/testOnly goldengate.tests.TechSpecMemorySpec"
```

Result on 2026-11-09: **5 succeeded, 0 failed**, sbt `[success]` in 119 s. The spec elaborates `TechSpecMemoryModel` to Verilog with the 64-set retention table and the request trace, elaborates it again with the table and the trace removed, checks the illustrative register defaults, checks that `TechSpecByteNVM` selects `TechSpecMemoryConfig` with 32/32 entries and tracing off, and checks that `HBM2FRFCFS16GBDualPC` still selects an `HBMModelConfig` with one channel, two pseudo-channels, 16 banks per pseudo-channel, and tracing off.

Elaboration means the module builds and those config keys are intact. It does not mean the Chisel schedule matches `techspec.py`. That match is by construction of the two implementations and is unchecked until a metasim trace is diffed. The compile emitted the usual Chisel 3.6 deprecation warnings from Rocket Chip. They were not treated as errors.

## HBM behavior

No HBM RTL was edited. The spec above instantiates the existing `HBM2FRFCFS16GBDualPC` key and checks its organization fields. The Ramulator flow was not re-run. The previous 0-violation claim remains the claim in `sim/scripts/hbm-validation/README.md`, not a new measurement.

## Replay sanity

`replay_trace.py` refuses a trace that is not ordered by cycle, refuses an issuer schedule with overlapping service windows, and refuses to finish if any request was not admitted. The 18-point sample run completed and wrote the JSON cited in `WORKLOAD_CHARACTERIZATION.md`. Service 1 and service 4 produced identical counters on this trace. That is the occupancy rule, not a silent skip: every row has `axi_len = 3`, so both services occupy 4 beats.

## Not run

- FireSim metasim, Verilator, or GoldenGate of `TechSpecF2Config` or `PointerChaserTechSpec`
- Any FPGA bitstream or driver
- Ramulator
- A comparison of Chisel `printf` lines against the Python schedule
- A test that the runtime conf is accepted by a FASED driver
- Functional data values
- Two different host clocks or two target frequencies
