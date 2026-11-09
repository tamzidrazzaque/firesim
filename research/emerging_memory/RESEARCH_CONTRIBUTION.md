# Research contribution

## Evidence against the three hypotheses

**H1. Performance is limited by request parallelism and topology more than by peak device bandwidth.** Supported for the AXI4 fuzzer, not yet for Radiance. The 8-byte port can move 8 bytes per cycle. The fastest TechSpec run moved 0.49 bytes per traffic cycle. DDR3, HBM2, and a 30-cycle NVM finished within 1,521 target cycles of each other. At latency 200, changing the outstanding cap from 4 to 32 cut the traffic window from 9,726 cycles to 1,522. At latency 30, outstanding 8 is already within 8% of outstanding 32. Peak bandwidth is not the knob this master uses.

**H2. Different AI objects need different endurance and retention.** Not tested. The fuzzer is not an inference workload. The older MemPerf sample is 92.7% reads and 11,744 write bytes after the caches. That is one read-dominated window, not a split among weights, KV cache, and activations. Retention was left at 0, so no lifetime was measured.

**H3. A hybrid hierarchy helps.** Not tested. No second address region was added, and no Radiance run compared placements.

## Smallest next architecture change

Do not add a NAND controller or a new placement engine yet. The measurement that would justify one is a Radiance run in which raising MSHRs or the FASED outstanding cap moves target cycles, while swapping DDR3 for HBM2 does not. The two-SM config already has `WithMemParallelism` for that MSHR change. The missing piece is the controlled run, not a new RTL block.

If that run shows the opposite, and the GPU already fills the port, then the next mechanism is more bytes per cycle or more ports, which is a topology change rather than a scheduler.

## What is measured, and what is illustrative

Measured this session: FASED Verilator target cycles, pass/fail of the data checker, TechSpec admit traces, and the HBM/TechSpec beat counts.

Illustrative: the latency-30 card, every swept latency and service value, and any endurance or retention statement. The FeFET 139 ns sense estimate was not loaded into the model.

Not measured: Radiance, STREAM, GEMM, prefill, decode, FPGA host time, energy, and a calibrated retention time.
