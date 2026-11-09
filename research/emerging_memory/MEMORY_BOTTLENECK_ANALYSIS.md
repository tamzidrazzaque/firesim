# Memory bottleneck analysis

All numbers are the TechSpec metasim of the 200-transaction AXI4 fuzzer. The first admit is cycle 524,389 in every run. "Traffic cycles" means passed cycle minus that admit.

| Latency | Service | Outstanding cap | Traffic cycles | Issuer busy cycles | Bytes / traffic cycle |
|---:|---:|---:|---:|---:|---:|
| 30 | 1 | 32 | 1,050 | 227 | 0.489 |
| 30 | 1 | 8 | 1,129 | 227 | 0.454 |
| 30 | 1 | 4 | 1,620 | 227 | 0.317 |
| 200 | 1 | 32 | 1,522 | 227 | 0.337 |
| 200 | 1 | 4 | 9,726 | 227 | 0.053 |
| 1000 | 1 | 32 | 6,338 | 227 | 0.081 |
| 30 | 32 | 32 | 6,459 | 6,400 | 0.079 |

191 of the 200 admits are single-beat (`axi_len = 0`). Service 1 therefore occupies one cycle per admit, and issuer-busy stays at 227 cycles until the programmed service rises to 32. At service 32 the issuer is busy for 6,400 of the 6,459 traffic cycles. That run is service-bound.

## Which knob moves the result

At latency 30, outstanding 8 (1,129 cycles) is 7.5% above outstanding 32 (1,050). Outstanding 4 is 54% above outstanding 32. For this short-latency point, depth beyond 8 stops helping.

At latency 200, outstanding 4 takes 9,726 traffic cycles and outstanding 32 takes 1,522. That is a 6.4× reduction from raising the cap, larger than the move from latency 200 to latency 30 at a cap of 32 (1,522 to 1,050).

Latency 1000 at outstanding 32 still takes 6,338 traffic cycles, six times the latency-30 baseline. Latency matters once responses stay in flight longer than the fuzzer's natural gap, and the outstanding cap decides whether those responses queue.

The 8-byte port can move 8 bytes per target cycle. The fastest measured point moves 0.49 bytes per traffic cycle. Raising device service rate from "one beat per cycle" does nothing more for this master. Slowing it to 32 cycles per request does: traffic cycles grow from 1,050 to 6,459.

On the three-model comparison, with each model's own hardware defaults, DDR3 and HBM2 land 570 and 1,521 cycles above the latency-30 TechSpec run. The name of the DRAM technology moves this fuzzer less than outstanding depth does once latency is 200 cycles.

Figures: `results/latency_sensitivity.png`, `results/throughput_vs_outstanding.png` (same three-panel figure), `results/memory_bandwidth_saturation.png`.
