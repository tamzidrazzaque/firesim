# Workload requirements

## This session's fuzzer

The AXI4 fuzzer is a functional traffic generator. It is not an inference workload.

On the latency-30 TechSpec run:

- 190 reads, 10 writes
- 483 read bytes, 30 write bytes
- 63 distinct addresses in the trace, but 133 of 200 admits and 6 of 10 writes are address 0
- `enduranceExceeded` stayed 0 because `enduranceLimitBytes` was 0
- retention class counters stayed 0 because `retentionCycles` was 0

A lifetime calculated from 10 writes would be an extrapolation of a testbench, not a device requirement. The counters did not corrupt data. They are diagnostics.

## Prior Radiance MemPerf sample

The checked-in sample `sim/scripts/hbm-validation/examples/radiance-memperf-reqtrace-sample.csv` was parsed in the previous session and was not regenerated. It is 5,000 HBM admits from a Radiance MemPerf metasim, not a new run and not an LLM.

- 4,633 reads and 367 writes (92.7% reads)
- 148,256 read bytes and 11,744 write bytes
- every burst is 32 bytes (`axi_len = 3` on an 8-byte port)
- about one admit every 33 target cycles

That write volume, 367 writes and 11,744 bytes, is what reached the HBM model after the caches. It is not the count of GPU store instructions. A byte-addressable memory whose endurance budget is exhausted by a few hundred writes would be inadequate for even this short sample. A budget of millions of writes is not stressed by 367 writes. No physical write amplification is in the model, so this is not a lifetime in years.

The sample does not say how long a weight must remain valid. Reads were not treated as refreshes. Retention was not enabled. The only statement the trace supports is that this window is read-dominated and the writes that do reach memory are a small byte count.

No prefill-versus-decode split exists in the trace. Calling it an LLM result would be wrong.
