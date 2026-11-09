# Next milestones

The working tree is FireSim `investigation/hbm2-fixed-work` at `8ee72392`, plus the uncommitted technology-spec model. The Chipyard handoff still gitlinks FireSim `09759334`. Nothing in this session was run on an FPGA.

## Immediate next step

Run a metasim of `TechSpecF2Config` or `PointerChaserTechSpec` with `techspec-illustrative-byte-nvm.conf`, capture `TECHSPEC` lines, and diff `start` and `release` against `techspec.py` on the same AXI requests. That is the check that the Chisel schedule and the Python schedule are the same model. Elaboration does not provide it. The outstanding-cap difference between the timing-model sink and the target AXI last beat should be measured in that log, not assumed away.

JDK 17 and sbt 1.10.1 are installed under `/global/home/tamzid_razzaque/sagar_memory/toolchains/`. The system `java` is 8 and will not build this tree. Platform FPGA submodules are not initialized. A metasim of fasedtests does not need them. A full Radiance metasim needs the Chipyard submodules and a FireSim pin bump.

## Three experiments, in order

1. **Metasim schedule diff.** One bridge, the illustrative card, a few hundred directed AXI requests: single beat, 4-beat burst, read and write in one cycle, queue full, endurance flag set, one retention hit and one conflict miss. Compare to the Python tests that already pass. This either confirms the Chisel or finds the egress-delay mismatch.

2. **Closed-loop swap on the existing two-SM target.** Keep `FireSimE4M3MxGemminiTwoClusterHBMRadianceConfig`, the ELF, and the caches fixed. Run the same FixedReadProbe or STREAM Copy smoke three times on DDR3-2133, HBM2-2000, and `TechSpecByteNVM` at latency 30 and at latency 200, with outstanding 4 and 32. Report target cycles, bytes, and `issuerBusyCycles`. This is the experiment that can support or weaken hypothesis 1. Do not retune the L2 in the same run.

3. **Outstanding-depth sweep on that same binary.** The sample says the cap matters more than service 1 versus service 4 for 32-byte bursts. Repeat the closed-loop workload at outstanding 4, 8, and 32. If the GPU's own MSHRs never present more than a handful of misses, the FASED cap will not show up, and the right knob is the cache, which is a different experiment and should be named as such.

## Technologies after that

- HBM2-2000 and HBM2-2400 remain the DRAM baselines. The HBM4-8000 table is already in the model and should be labeled as a table on the HBM2 state machine, with the fills documented in `HBMModel.scala`, before anyone calls a run "HBM4."
- DDR5 is a JEDEC table on the existing DRAM machine once a specific speed grade is chosen. It is not the next model.
- A byte-addressable emerging card replaces the illustrative JSON when a measured latency, service time, and retention or endurance distribution exists. Until then the status stays `illustrative-sensitivity`.
- A NAND or FeNAND string model is a new key with page or string granularity. It should not be attached as a substitute for the Radiance L2 port. The native Spectre string results in `/global/home/tamzid_razzaque/fifth_yr_memory/experiments/native_spectre_fefet/` are the device input for that later key, after retention is calibrated.

## Blockers that need a person

- An FPGA slot. `chipyard/investigation/README.md` says the XB10 host is shared and should not be programmed without an owner. This session did not ask for a slot.
- The Chipyard submodule bump onto FireSim `8ee72392` plus this model, if the closed-loop run is to include it. That is a gitlink change and should be a deliberate commit.
- A calibrated FeFET retention and endurance source from the Salahuddin group. The framework does not need it for experiments 1-3. The illustrative card must keep its label until that source exists.

## Question for Sagar

For the first closed-loop comparison, should the new model replace the timing on the existing five Radiance region ports, or should it be an additional address region the GPU can use as weight or KV storage while the L2 stays on HBM or DDR?
