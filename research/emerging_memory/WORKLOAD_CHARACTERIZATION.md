# Workload characterization

No new Radiance, Gemmini, STREAM, or Llama run was launched. The kernel clone on `hbm-gemm-e2e` has `soc/muon.elf` and does not contain the STREAM/Spatter ELF matrix described in `chipyard/investigation/workloads.md`. The characterization below uses the HBM request trace already checked into FireSim, plus the prior host-Verilator numbers cited in `EXISTING_INFRASTRUCTURE.md`.

## Trace that was replayed

`sim/scripts/hbm-validation/examples/radiance-memperf-reqtrace-sample.csv`

The validation README calls this a sample of a Radiance MemPerf metasim. The file has 5,000 data rows. The companion `radiance-memperf-segments.txt` describes a longer run of 613,255 requests. The replay is the 5,000-row sample only.

| Quantity | Value |
|---|---|
| Rows | 5,000 |
| Reads / writes | 4,633 / 367 (92.7% reads) |
| AXI length | 3 on every row |
| Assumed AXI size | 3 (8-byte beats). The CSV has no size field. The fasedtests and Radiance memory ports in this tree are 8-byte beats, and length 3 is a 32-byte burst. |
| Bytes | 148,256 read, 11,744 write, 160,000 total |
| First offer cycle | 2,051 |
| Last offer cycle | 165,474 |
| Offer-window length | 163,423 target cycles |
| Mean offer rate | 0.0306 requests/cycle, about one 32-byte request every 33 cycles |

At occupancy 4 the issuer is busy for 20,000 cycles, which is 5,000 requests times 4 beats. Over the 163,453-cycle schedule span of the latency-30 run, that is about 12% busy. The captured admit stream is sparse. This is the stream after the Radiance caches. It is not the rate of every Muon load.

`radiance-memperf-segments.txt` shows the same kind of rate on the long run. Segment 0 is 12,268 requests in 494,345 cycles. Segment 5 is 179,177 requests in 5,640,298 cycles. Both are a few requests per hundred cycles at the HBM model. The sample is not a dense microbenchmark, and it is not proof that every kernel looks like this.

## Open-loop replay

`replay_trace.py` offers each sample request to `TechSpecModel` at the cycle the HBM model admitted it. If the cap is full, the request waits. Reads and writes are offered independently. The script does not rerun the GPU, the L2, or the HBM scheduler. Issue times stay on the original schedule until the new model refuses them. A closed-loop core would have issued later requests later. Wait counts from this replay are a lower bound on how a slower device would move a dependent core, and they are the actual extra admit delay of this frozen schedule.

The card's endurance limit and retention window stayed 0. No energy was computed. The run is FireSim commit `8ee72392` plus the uncommitted model, Python 3, the JSON next to this note.

Mean cycles a request waited before admit:

| Latency | Service | Outstanding | Mean wait | Issuer busy cycles | Schedule span |
|---:|---:|---:|---:|---:|---:|
| 30 | 1 | 4 | 0 | 20,000 | 163,453 |
| 30 | 1 | 32 | 0 | 20,000 | 163,453 |
| 30 | 4 | 4 | 0 | 20,000 | 163,453 |
| 30 | 4 | 32 | 0 | 20,000 | 163,453 |
| 30 | 32 | 4 | 2,415.0 | 159,998 | 163,639 |
| 30 | 32 | 32 | 1,699.9 | 159,998 | 163,639 |
| 200 | 1 | 4 | 37,957.1 | 20,000 | 231,807 |
| 200 | 1 | 32 | 0 | 20,000 | 163,623 |
| 200 | 4 | 4 | 37,957.1 | 20,000 | 231,807 |
| 200 | 4 | 32 | 0 | 20,000 | 163,623 |
| 200 | 32 | 4 | 39,602.3 | 160,000 | 235,255 |
| 200 | 32 | 32 | 1,823.2 | 160,000 | 163,809 |
| 1000 | 1 | 4 | 466,961.0 | 20,000 | 1,159,002 |
| 1000 | 1 | 32 | 1,199.7 | 20,000 | 164,423 |
| 1000 | 4 | 4 | 466,961.0 | 20,000 | 1,159,002 |
| 1000 | 4 | 32 | 1,199.7 | 20,000 | 164,423 |
| 1000 | 32 | 4 | 467,078.2 | 160,000 | 1,159,040 |
| 1000 | 32 | 32 | 2,430.2 | 160,000 | 164,609 |

Service 1 and service 4 match on every row. Occupancy is `max(service, axi_len+1)`, and `axi_len+1` is 4 for every request. A programmed service of 1 does not retire a 32-byte burst in one cycle on an 8-byte port. Service 32 is the first setting that is slower than the bus.

Figure: `results/techspec_sample_sensitivity.png`.

## How to read this against the earlier HBM study

The fixed-read probe moved 1,048,576 bytes of sequential 32-byte reads through one 8-byte port in about 143,000 to 145,000 target cycles, near 7.3 GB/s at a 1 GHz tick. That probe is port-limited. HBM2 and DDR3 differed by under 2%. Raising the memory's pin bandwidth does not move that number unless the model presents more bytes per target cycle.

The MemPerf sample is the other regime. The HBM model admitted 160 KB over 163k cycles. The issuer is busy about 12% of the time at a 4-beat occupancy. On that frozen schedule:

- Latency 30 with 4 or 32 outstanding entries never delays admission.
- Latency 200 still does not delay admission at 32 outstanding entries. It does delay admission by about 38,000 cycles per request at 4 outstanding entries, and the schedule span grows from 163k to 232k cycles.
- Latency 1000 at 4 outstanding entries stretches the span to 1.16M cycles. At 32 outstanding entries the mean admit wait is about 1,200 cycles and the span grows by roughly the added latency of the tail, not by 1,000 cycles times 5,000 requests.

So for this admit stream the outstanding cap decides whether a long latency becomes queueing. The 1-versus-4 service knob does not, because the bursts are already 4 beats. A 32-cycle service does, because the issuer is then busy for almost the whole window.

This does not say the GPU is insensitive to latency. The offer times already include whatever the GPU did under the HBM model. A load that misses and waits still pays the response latency even when the next request is admitted immediately. The replay does not model that consumer. It says the admit queue of this particular trace does not fill at 30 cycles, and it does fill when the device holds only 4 requests for 200 cycles or more.

## Other workloads

GEMM, STREAM, Spatter, and Llama/Gemma were not re-run. The prior STREAM Copy smoke (HBM2-2400 395,266 target cycles, DDR3-2133 386,050) is a tiny kernel on the five-bridge target. It is the same direction as the fixed-read probe: swapping the HBM2 table for DDR3 did not produce a large speedup. Llama prefill and decode are not in the checked-in ELF list used here.

The capacity of the host backing store is the FPGA DRAM image size, not a modeled 16 GB stack with a distinct retention cell. Addressability beyond that image is not emulated. The trace analysis is the stand-in.
