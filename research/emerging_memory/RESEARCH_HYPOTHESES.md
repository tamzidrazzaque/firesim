# Research hypotheses

The contribution this session can support is a framework extension plus a workload observation. It is not a new accelerator, and it is not a claim that a particular emerging memory wins.

## What already exists in the literature and in this repo

FireSim/FASED already models a latency pipe, a bank-conflict pipe, DDR3 FR-FCFS, and HBM2, with runtime timing registers and a Ramulator legality check. Ramulator, DRAMSim, and gem5's memory system already sweep DRAM timing outside an FPGA. Publishing another DRAM table would overlap that work. The gap Sagar described is a place to put a non-DRAM card, including endurance and retention, and to run it under a real Radiance or Gemmini workload without deciding the system hookup in advance.

A FeNAND string current from BSIM-FEBDMC is a device result. It is not a memory-system result, and the default-`TAU0` retention behavior is not calibrated. Treating it as a system specification would over-claim.

## Hypotheses

1. **Peak pin bandwidth and a single latency number do not predict whether a memory helps an inference workload.** This is the hypothesis the existing evidence actually speaks to. On equal 8-byte FASED ports, HBM2-2000 took 1.7% more cycles than DDR3-2133 for a sequential 1 MB read (`hbm-fixed-work-diagnostic-2026-10-21.md`). The MemPerf sample's admit stream keeps a 4-beat issuer busy about 12% of the window. Service 1 and service 4 are the same knob on that trace. Latency shows up as admit queueing only when the outstanding cap is small relative to the response time. A closed-loop confirmation is still missing: the replay does not move the GPU's issue times.

2. **Write, read, and locality patterns set endurance and retention requirements that a bandwidth number does not.** The sample is 92.7% reads and 11,744 write bytes. A write-endurance budget sized from that trace would look easy, and a decode workload with a different write stream could look different. The counters can record this. The replay left the budget at 0, so hypothesis 2 is a measurement the model can make and not a result yet. The retention monitor was also left disabled.

3. **Prefill and decode want different memories and different places in the hierarchy.** No prefill or decode run exists in this session. The two-SM target's split L2 is one placement. A separate weight port would be another. Neither was compared.

4. **An FPGA-hosted model can compare technologies that a compact-model transient cannot.** The framework shape is in place: one bridge, several `MemModelKey` values, a card file, and a checker. The technology-spec model has not itself run on an FPGA or in metasim. The HBM model has. Hypothesis 4 is the reason to build the slice. It is not yet demonstrated for a non-DRAM card.

5. **A scheduler can hide a technology constraint.** The HBM REFSB result is the existing example: sequential traffic was much slower than bank-interleaved traffic under the same timing, and a one-line change to the refresh gate did not remove that gap. The technology-spec issuer has no scheduler beyond read-before-write in a tie. Hypothesis 5 is supported for HBM refresh by the October diagnostic. It is not supported for endurance or retention, because those flags do not affect scheduling.

## What would make a paper

A paper needs a closed-loop result on one unchanged Radiance target, with two or more cards, where the only intentional change is the FASED model and its runtime profile. The result has to include target cycles, achieved bytes, outstanding occupancy, and the model's own counters, and it has to say when a higher pin bandwidth did nothing. A calibrated device card is not required for the first paper if every non-DRAM number is labeled as a sensitivity and the DRAM baselines are the existing HBM2 and DDR3 profiles. A calibrated card would make a second, stronger claim.

The framework piece is the card, the issuer model, and the rule that reliability counters do not silently corrupt data. The workload piece is the comparison. There is no new hardware mechanism in this slice.

## Hypothesis to lead with

Hypothesis 1. The fixed-read probe and the MemPerf admit stream both say the same thing in different words: the bytes the GPU presents to one FASED port, and how many requests it leaves outstanding, decide the target cycles. The name of the memory technology does not.
