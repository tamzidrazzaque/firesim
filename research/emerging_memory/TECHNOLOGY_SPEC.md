# Technology specification

Version 1 of the card is `firesim/sim/scripts/emerging-memory/specs/illustrative_byte_addressable_nvm.json`. The Chisel register defaults and `techspec-illustrative-byte-nvm.conf` carry the same numbers. The status of every number in that card is **illustrative sensitivity**. Nothing in it was measured on a device.

## Where each field lives

| Field | Layer | Status in the v1 card |
|---|---|---|
| `technology_name`, `spec_version`, `provenance`, `calibration_status` | measurement metadata | illustrative-byte-addressable-nvm, version 1 |
| `addressability`, `organization` | device model | byte address, no banks and no pages |
| `read_latency_cycles`, `write_latency_cycles` | device timing, programmed into the timing model | 30 target cycles, the existing latency-pipe default |
| `read_service_cycles`, `write_service_cycles`, `issuer_occupancy_rule` | device timing | service 1; occupancy is `max(service, axi_len+1)` |
| `outstanding_reads`, `outstanding_writes` | controller / bridge queue | 32, from `WithFuncModelLimits` |
| `data_width_bytes_assumed_by_replay`, `axi_size_assumed_by_replay` | system interface assumption used only by the open-loop replay | 8-byte beats, AXI size 3 |
| `endurance_limit_bytes`, `endurance_policy` | reliability model | limit 0, account only |
| `write_amplification` | reliability model | null. The implementation forces logical and device write bytes to match. |
| `retention_cycles`, `retention_sets`, `retention_granularity_bytes`, `retention_policy` | reliability model | window 0 so classification is off; the hardware can hold 64 sets of 64-byte lines |
| `energy_per_read_joules`, `energy_per_write_joules`, `temperature` | not modeled | null |

A published JEDEC table, such as the HBM2-2400 counts already in `HBMTimingTables`, stays in the DRAM model. It is not copied into this card. An extrapolation or a sensitivity knob has to say so in `calibration_status`. The v1 card says `illustrative-sensitivity`.

## Policies that are part of the spec

**Endurance.** The model counts AXI write bytes at the cycle a write is admitted to the issuer (`(axi_len+1) << axi_size`). That count is both the logical write traffic and the device write traffic. When the programmed budget is nonzero and the next write would pass it, `enduranceExceeded` sticks at 1. Timing and data are unchanged. The model does not remap, wear-level, or fail the write. Spatial hot spots are invisible: the counter is the whole device.

**Retention.** The model does not flip bits when a window expires. With a nonzero window and a nonzero set count, it classifies admitted reads against a direct-mapped timestamp sample. Unknown means "this line is not in the sample," which includes lines that were never written in the sample and lines evicted by a conflict. Unknown is not a detected error. The timestamp is the admit cycle of the write, not a separate program-complete event.

**Functional data.** Bytes live in the FASED host-DRAM backing store. This spec does not describe that store and does not inject errors into it.

## What is deliberately absent

No FeFET read current, memory window, `TAU0`, endurance cycle rating, or retention time is in the card. The Berkeley BSIM-FEBDMC work on this machine lives in `/global/home/tamzid_razzaque/fifth_yr_memory/`. Native Spectre already runs there (`experiments/native_spectre_fefet/`), and the retention behavior under the model's default `TAU0` of 100 ps is not a calibrated memory lifetime. Professor Salahuddin has said that calibration still needs the right person. This framework does not wait on that calibration and does not treat a frozen-polarization current as a retention result.

A later calibrated card can replace the JSON and the `+mm_*` values without a new Chisel class, as long as the device remains byte-addressable and the occupancy rule still describes it. A page-programmed NAND or a FeNAND string is a different organization and needs a different model. The native string study is evidence about cell current versus string length. It is not a system address map.

## Route from a device result to this card

1. A Spectre or measured distribution produces a latency, a service time, and a retention or endurance distribution at a stated temperature and bias.
2. The distribution is reduced to a card whose `calibration_status` says measured, published, extrapolated, or illustrative, with the source named in `provenance`.
3. The card is written as `+mm_*` registers on a FASED bridge.
4. A closed-loop workload reports target cycles, admit stalls, and the model's own counters.

Step 2 is where a sensitivity range is allowed. The v1 card is that kind of range, and the only range it varies in the study below is latency, service, and outstanding depth. Endurance and retention stay at their disabled defaults in the replay, so the replay is not a reliability result.
