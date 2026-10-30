# Testing

## 2026-10-30 frozen Chisel checker

The checker lives in `independent/cleanroom/` and is not part of the
earlier `independent/rpc_fased` package. Its own suite is:

```bash
cd independent/cleanroom
# JDK 11, sbt 1.10.2, from a workspace that already resolved Chisel 3.6.0
sbt -batch test
sbt -batch "runMain rpc.Replay --tck-ps 1250 --refresh-select 0 spec/selftest.jsonl"
```

The saved run is `independent/cleanroom/results/sbt-test.txt` (63 tests,
0 failures). ETH pin logs are replayed, without moving their cycles, by:

```bash
python3 scripts/run_chisel_eth_replay.py --skip-chisel \
  --cleanroom independent/cleanroom \
  results/logs/eth_full_pin_run.log \
  results/logs/chipyard_eth_timing_rocket_stdout.log \
  results/logs/chipyard_eth_timing_boom_stdout.log \
  results/logs/eth_timing_directed_run.log \
  results/logs/eth_timing_directed_negative.log \
  results/logs/eth_timing_directed_borderline.log \
  results/logs/eth_timing_directed_stress.log
```

The command above exports JSONL and runs the older Python checker. The
Chisel results already collected from those JSONL files are
`results/differential/chisel-replay/chisel_summary.json`. Replaying
again requires the cleanroom's sbt cache or a fresh `sbt` resolve, then
`runMain rpc.Replay --tck-ps 5000 --refresh-select <0|1|2> <jsonl>`.
The script exchanges the two 16-bit packet halves so the pin log matches
`independent/cleanroom/docs/PACKET.md`.

`./scripts/run_eth_timing_directed.sh` now also passes `+stress`. Rocket
and BOOM were rerun from the existing simulators; the pin commands match
`results/logs/chipyard_eth_timing_{rocket,boom}_stdout.log`.

## 2026-10-30 same-profile differential checks

`./scripts/run_sv_spec_checks.sh --with-eth` passed after preserving the
2026-10-28 pin and directed logs in `results/logs/archive/20261028/`.
The baseline script now runs tests that do not depend on generated fuzzer or
core logs. The full suite, including those artifact-dependent checks, also
passed with the existing logs:

```bash
.venv/bin/python -m pytest -q tests independent/rpc_fased/tests independent/tests_eth_check.py
.venv/bin/python scripts/verify_rpc_trace_evidence.py
```

The trace replay checked 21 standalone ETH commands, 394 Rocket commands,
409 BOOM commands, 57 directed legal-REF commands, 45 deliberately short-REF
commands, and 45 intermediate-wait commands. The positive traces have no
independent violations under either refresh reading. The short wait has one
`tREFI` violation under both readings, offered at cycle 42571. With
`N_REF=20`, the controller issues the next ACT at REF+32 CK (cycle 42587):
the one-tREFI reading accepts it, while the row-step checker and SV observer
reject it with earliest legal cycle 124475. This is a disagreement between
documented refresh interpretations, not proof of a hardware failure. The
JSONL exports and SHA-256 report are under
`results/differential/rpc-traces/`.
The directed run also held the AXI R response under seven cycles of
backpressure and checked that valid, data, ID, last, and response remained
stable (`PASS AXI read backpressure` in its log). The earlier directed logs
are preserved under `results/logs/archive/20261030_pre_backpressure/`.

The existing `IndRpcDramF2ReqTraceConfig` Verilator binary was run with
`configs/indrpc-200-closed.conf` and
`configs/indrpc-200-closed-refresh.conf`, adding `_0` to each runtime
plusarg name. The runs exited zero and printed `*** PASSED ***` after
933,979 and 1,237,270 cycles, respectively. The first emitted 30,000
ACT/column/PRE commands; the second emitted those commands plus one REF at
cycle 500,000 with a 327,680-CK stall. The exact replay commands are:

```bash
.venv/bin/python scripts/compare_ind_fased.py results/logs/indrpc_200_closed.log --tck-ps 5000 --cl 8 --page-policy closed
.venv/bin/python scripts/compare_ind_fased.py results/logs/indrpc_200_closed_refresh.log --tck-ps 5000 --cl 8 --page-policy closed
```

Both reported zero violations. The fuzzer's success string does not compare
returned memory bytes. See `docs/VALIDATION_2026-10-30.md` for the status
matrix, provenance, and remaining boundaries.

## Current SV handoff (2026-10-28)

Use `docs/SV_VERIFICATION_HANDOFF.md` for the supported modes and the
specification decisions. The current commands are:

```bash
./scripts/run_sv_spec_checks.sh --with-eth
./scripts/run_chipyard_eth_timing.sh rocket
./scripts/run_chipyard_eth_timing.sh boom
```

The first command runs the HyperRAM pin model test, the RPC timing observer
test, Python tests, and both the legal/intentional-illegal ETH REF runs.
The core scripts rebuild the Chipyard harness and require the workload's
success branch with `FATAL_ON_VIOLATION=1`. The sections below preserve the
earlier 2026-10-25 and 2026-10-23 evidence; the N_REF=2 failure there was
the diagnosed configuration defect, now covered by the negative test.

The 2026-10-28 independent FireSim rebuild is in
`results/logs/midas_spec_compile.log` and `indrpc_spec_verilator.log`.
`indrpc_spec_open.log` passed after 1,033,717 cycles; replaying its 28,623
commands with `scripts/compare_ind_fased.py` found zero violations.
`indrpc_spec_refresh.log` passed after 3,630,727 cycles; replaying 28,624
events, including two 1,310,720-CK one-shot REF stalls, also found zero
violations. These are scheduler/command checks, not a FASED read-data compare.

## Independent timing replay (2026-10-25)

The checker reads `RPC_PIN_CMD` lines. It does not rebuild Chipyard and it
does not change the controller.

```bash
cd independent
../.venv/bin/python -m unittest discover -s rpc_fased/tests -q
../.venv/bin/python -m unittest tests_eth_check.py -q
cd ..
./scripts/check_eth_independent_timing.sh
./scripts/run_eth_timing_directed.sh
```

The unit commands are the speed-1600 suite (29 tests, including both refresh
readings) and the 5 ns replay plus injected faults. The directed script
builds `tb_eth_timing_directed` and writes
`results/logs/eth_timing_directed_run.log`. That run is the live observer.
With N_REF=2 it reports `tREFI`. With `n_ref_4=327680` the following ACT is
legal for the row-step reading.

The separate FASED model:

```bash
cd third_party/firesim/sim
# conda fsim, FIRESIM_ENV_SOURCED=1, firtool 1.75.0, RISCV set, conda include/lib
make TARGET_PROJECT=fasedtests TARGET_CONFIG=DefaultConfig \
  PLATFORM_CONFIG=IndRpcDramF2ReqTraceConfig verilator
```

`configs/indrpc-1600-open.conf` is the no-refresh trace compared by
`scripts/compare_ind_fased.py`. `configs/indrpc-1600-refresh.conf` is the
one-refresh trace. Exit 0 of the fuzzer is not a data compare.

Rocket and BOOM with the observer linked into the harness:

```bash
./scripts/run_chipyard_eth_timing.sh rocket
./scripts/run_chipyard_eth_timing.sh boom
```

Those logs are `results/logs/chipyard_eth_timing_rocket_stdout.log` and
`results/logs/chipyard_eth_timing_boom_stdout.log`. They do not replace the
2026-10-23 logs.

## Full ETH pin path (2026-10-23)

The Etron [EM6GA16L Rev. 1.4 datasheet](https://etron.com/wp-content/uploads/2022/04/EM6GA16LGDBXCAEA-RPC1-DRAM-Induatrial_Rev.-1.4.pdf)
specifies a 32-byte RPC word sent over eight clock cycles, two active-low
write-mask cycles, and CL/AL and bank timing. The digital device model checks
the RESET/PRE/MRS/ZQC startup order and delays, packet framing, data/mask
drive, open rows, and tRP/tRCD/tRAS. It stores bytes
from DB pins and returns them through DB/DQS pins.

```bash
./scripts/setup_eth_deps.sh
./scripts/run_eth_full_pin.sh
./scripts/run_chipyard_eth_pin.sh rocket
./scripts/run_chipyard_eth_pin.sh boom
```

`run_chipyard_eth_pin.sh` installs the harness source from `integration/chipyard/`
into the isolated `third_party/chipyard-rocket` checkout and builds Chipyard's
standard Verilator simulator. Its target ELF is `workloads/rpc_banks.riscv`.
The Chipyard `TestDriver.v:158` finish is the success branch; the failure
branch is line 147. `+verbose` is intentionally omitted because it enables
all core debug printfs.

| Check | Result | Log |
|---|---|---|
| Standalone complete ETH top | PASS: full 8-byte write/read, partial-byte overwrite, 64-byte burst | `results/logs/eth_full_pin_run.log` |
| Rocket through ETH and pin memory | PASS: workload success, ACT/RD on banks 0–3 | `results/logs/chipyard_eth_rocket_stdout.log` |
| BOOM through ETH and pin memory | PASS: workload success, ACT/RD on banks 0–3 | `results/logs/chipyard_eth_boom_stdout.log` |

The first Rocket run failed because the ETH upsizer requires AXI CACHE[1] to
change burst geometry. Chipyard left that hint low. The harness sets it for
DRAM traffic; the standalone test also runs with that bit set. Both cores now
complete the workload. The model is digital and does not cover analog margins,
full initialization electrical checks, long-run refresh, or every timing
corner.

## 2026-10-23 core and ETH integration checks

The ETH directed test is `./scripts/run_eth_data.sh`. It instantiates the production `rpc_interface` serializer, parallelizer, 64-to-256-bit upsizer, buffers and mask handling, then the production `rpc_cmd_fsm`, with a transaction-side 256-bit behavioral memory. It checks write/read data, byte masks, AXI IDs, and ACT/CAS/PRE commands on all four banks. Result: **PASS**, `results/logs/eth_interface_data.log`. The standalone `rpc_synth_wrap` lint has zero errors (`results/logs/eth_full_top_lint.log`). Neither check simulates a PHY/device pin interface.

`workloads/rpc_banks.c` writes and reads 64 words per bank at 0x80010000, 0x80810000, 0x81010000 and 0x81810000, returning a nonzero exit code on a mismatch. `workloads/rpc_banks.riscv` was built with the local `riscv64-unknown-elf-gcc -march=rv64imafd -mabi=lp64d -O2 -static -specs=htif_nano.specs`. It passes Spike (`results/logs/rpc_banks_spike.log`) and baseline Chipyard Rocket (`results/logs/rocket_baseline_target.out`).

The isolated Chipyard copy is `third_party/chipyard-rocket`. `./scripts/apply_chipyard_fased.sh` installs the existing model/config sources there. The existing FireSim Makefile built Rocket (`FireSimRocketConfig`) and BOOM (`FireSimLargeBoomConfig`) Verilator targets with `PLATFORM_CONFIG=RpcDram256Mb_BaseF1Config`; the traced Rocket target uses `WithRpcDramRequestTrace_RpcDram256Mb_BaseF1Config`. Build logs are `results/logs/chipyard_rocket_rpc_compile.log`, `chipyard_rocket_rpc_verilator.log`, `chipyard_boom_rpc_compile.log`, `chipyard_boom_rpc_verilator.log`, and `chipyard_rocket_rpc_trace_clean_rebuild.log`.

The Chipyard builds used its existing `make ... verilator` target from `third_party/chipyard-rocket/sims/firesim/sim`, with `TARGET_PROJECT_MAKEFRAG=/scratch/trazzaque/memory-peripherals/third_party/chipyard-rocket/generators/firechip/chip/src/main/makefrag/firesim`, `PLATFORM=f1`, `TARGET_CONFIG` and `PLATFORM_CONFIG` as named above. The `fsim` conda environment supplied Verilator and firtool; `RISCV=/scratch/trazzaque/tools/riscv`, `FIRESIM_ENV_SOURCED=1`, and the conda include/library paths were exported. The build was entirely in the isolated copy.

Run the built targets with `./scripts/run_chipyard_rpc_workload.sh rocket` and `./scripts/run_chipyard_rpc_workload.sh boom`. Both use `configs/rpcdram-200-closed.conf`, with the FASED instance suffix `_0` added to each plusarg. Rocket **PASS** after 10,882 target cycles (`results/logs/rocket_rpc_target.out`); BOOM **PASS** after 6,274 (`results/logs/boom_rpc_target.out`). The Rocket trace has 97 `RPCREQ` entries, including addresses in banks 0–3. The FASED model is the core's memory bridge here; ETH controller RTL is not in these SoC simulations.

The first core runs hung because the runtime config set read/write request limits to 32 while the generated model's maximum was 10. The register width truncated 32 to zero, holding AXI ready low. Both RPC config files now set 10. The separate ETH bench exposed an ACT bank error and the correction is saved in `patches/eth_rpc_cmd_fsm_act_addr.patch`; the original ETH source tree was not changed.

The sections below record the earlier 2026-10-16 checks. The 2026-10-23 Python rerun passed all 32 collected tests; its log is `results/logs/pytest_20261023.txt`.

## Python

```bash
.venv/bin/python -m pytest tests -q --tb=short
```

Result: **PASS** (32 passed). Log: `results/logs/pytest.txt`. Configuration is the default constructors unless a test says otherwise. Seeds: HyperRAM random `0xC0FFEE`, RPC random and characterization `20261016`.

| Test | What it checks |
|---|---|
| `test_hyperram.py::test_power_on_defaults_and_reset_timing` | CR0 `0x8F2F`, L=7, fixed latency, 32 B wrap, tRP+tRH = 80 CK |
| `test_read_after_write_and_masks` | Data and RWDS byte mask |
| `test_linear_wrap_hybrid_and_capacity` | Wrapped, linear, hybrid, last bytes, out-of-range address |
| `test_registers_are_sticky_and_id_is_readonly` | CR0/CR1 writes, ID write ignored |
| `test_fixed_and_variable_latency_match_the_spec` | Fixed first-byte latency 17 CK; variable 10 CK (3+7) |
| `test_read_to_write_gap_is_tRWR_and_same_direction_is_tCSHI` | 7 CK after a read, 2 CK between writes |
| `test_short_gap_is_a_violation_and_tcsm_is_enforced` | Early CS# is a violation; FASED splits a 4 KB burst so no chip-select exceeds tCSM |
| `test_refresh_collision_appears_only_after_the_debt_builds` | First variable-latency read is 1x; a later one is 2x; a long idle returns to 1x |
| `test_fased_ordering_back_to_back_and_random_seed` | In-order AXI data, including random mixed traffic |
| `test_deep_power_down_blocks_memory_until_reset` | CR0[15]=0 blocks, reset clears |
| `test_rpcdram.py::test_geometry_and_catalog` | 4×4096×2 KB, tRCD=11, RL=12, ETH address map |
| `test_packet_bits_match_the_datasheet_and_the_eth_decoder_map` | Parallel-packet bits and the 32-bit ETH command word |
| `test_initialization_respects_power_up_delays` | PRE, MRS, ZQC after 200 µs + 5 µs, no violations |
| `test_illegal_sequences_are_reported` | Closed-bank read, tRCD, ACT-to-open, tRRD |
| `test_read_after_write_masks_banks_and_page_wrap` | Two banks, byte enables, a transfer that crosses a 2 KB page |
| `test_row_hit_and_row_miss_latency` | Miss = tRCD+RL = 23 CK; hit = RL = 12 CK |
| `test_closed_page_matches_eth_act_cas_pre_and_streaming_approaches_peak` | Closed page is ACT/RD/PRE; a full-page read is above 90% of 3200 MB/s |
| `test_back_to_back_streaming_has_no_data_bubble` | Serial reads abut on the data bus |
| `test_refresh_stall_and_200mhz_profile` | Four-bank FST stall; at 200 MHz the first CAS is tPPD-limited |
| `test_random_traffic_matches_a_shadow` | 40 random accesses against an independent byte array |
| `test_scheduler_refuses_to_emit_an_early_cas` | A legal RD at tRCD passes; a serial RD off the 8 CK grid fails |
| `test_calibration_and_eval.py` | Synthetic fitter recovers L=7 and RL=12; illegal RPC trace fails; safe probes pass |

## Verilator

```bash
./scripts/run_tests.sh
```

The RTL half of that script was also run directly. Logs:

| Command | Result | Log | What it shows |
|---|---|---|---|
| `rtl/obj_hyper/Vtb_hyperram` | PASS | `results/logs/rtl_hyperram.txt` (also stdout of the direct run) | Fixed-latency first response is 17 cycles; write, read, and a masked write |
| `rtl/obj_rpc/Vtb_rpc` | PASS | `results/logs/rtl_rpc.txt` | Closed-bank read and an early write are errors; a write after 11 cycles reads back |
| `rtl/obj_eth/Vtb_eth` | PASS | `results/logs/rtl_eth_decoder.txt` | ETH `rpc_cmd_decoder` classifies ACT, RD, WR, PRE, REF, ZQC, RESET the way our encoder builds them |

The HyperRAM and RPC RTL benches are transaction-level. They are not the PHY. The ETH test instantiates `rpc_cmd_decoder.sv` from the controller tree and does not modify it. It does not run the PHY or move data through `rpc.sv`.

## Characterization

```bash
.venv/bin/python scripts/characterize.py
```

Output: `results/characterization/performance.csv`, `hyperram_burst_bandwidth.png`, `sequential_compare.png`. Log: `results/logs/characterize.txt`.

Clock and source for every row: the model's tCK, converted as `bytes / cycles * 1e12 / tCK_ps`. Not an FPGA measurement.

| Workload | Config | Result |
|---|---|---|
| HyperRAM variable read, 32 B, 1 outstanding | 200 MHz, L=7 | 10 CK to first byte, 246 MB/s, 62% of 400 MB/s |
| HyperRAM variable read, 2048 B | same | 10 CK, 389 MB/s, 97% of 400 MB/s |
| HyperRAM fixed read, 32 B | power-on 2× latency | 17 CK, 194 MB/s, 48% of 400 MB/s |
| HyperRAM random 32 B | variable, seed 20261016 | 225 MB/s. Queued p50 of 888 CK is queue wait, not the device |
| RPC open page, 32×32 B sequential | speed-1600, RL=12 | 2936 MB/s, 92% of 3200 MB/s, p50 read latency 20 CK |
| RPC closed page, same traffic | speed-1600 | 615 MB/s, 19% of peak, p50 34 CK |
| RPC open page, 32×32 B | 200 MHz, RL=4 | 764 MB/s, 96% of 800 MB/s |
| RPC closed page, same | 200 MHz | 268 MB/s, 34% of 800 MB/s |
| RPC random rows, open or closed | speed-1600 | 613 MB/s. A new row every access, so the open page does not help |
| Four-bank fast refresh | speed-1600 | 1,310,720 CK = 1638 µs of stall |
| HBM2-2400 one channel | published pin ceiling | 38400 MB/s. Not re-simulated |

## Specification checks added this pass

| Test | Result | What it shows |
|---|---|---|
| `test_id0_matches_s80ks2562_section_6_2_1` | PASS | ID0 is `0x0E86`; a read returns `0x0E, 0x86` |
| `test_two_kib_read_is_split_to_honor_tcsm` | PASS | 2048 B at 200 MHz is two chip-selects. The longer one is 800 CK = 4.000 µs, equal to tCSM at ≤85 °C, not over it. At the >85 °C column (1 µs) the same read splits further. The 389 MB/s figure already includes these splits |
| `test_four_banks_are_independent_above_bit_23` | PASS | Banks 0–3 at bit 23 do not alias. The 22-bit fuzzer cannot reach these addresses |
| `test_fast_refresh_duration_matches_the_row_step_formula` | PASS | Stall is 4096 × 80 × 4 = 1,310,720 CK. An ACT inside the window is rejected. The next legal ACT is `busy_until + tRP` |
| `test_verilated_hyperram_gaps_match_the_chisel_formula` | PASS | All 10,000 Verilated accept deltas match the fixed-latency formula. Report: `results/differential/hyperram.txt` |

## What the fuzzer exit code proves

`AXI4Fuzzer` sets `error := false.B` (`sim/src/main/scala/fasedtests/AXI4Fuzzer.scala`). Exit 0 means every fuzzer raised `finished`. It does not mean read data matched. The run log still contains `AXI4FuzzMaster` lines marked `undefined`. Data checks are in the Python suite, which compares returned bytes to a shadow array.

## FireSim metasim

Both builds exited 0. Logs: `results/logs/hyperram-verilator.log`, `results/logs/rpc-verilator.log`.

```bash
cd /scratch/trazzaque/memory-peripherals/third_party/firesim/sim
# env: conda fsim, FIRESIM_ENV_SOURCED=1, firtool 1.75.0, SBT_OPTS pointed at this checkout
make TARGET_PROJECT=fasedtests TARGET_CONFIG=DefaultConfig \
  PLATFORM_CONFIG=HyperRAMF2ReqTraceConfig verilator
make TARGET_PROJECT=fasedtests TARGET_CONFIG=DefaultConfig \
  PLATFORM_CONFIG=RpcDramF2ReqTraceConfig verilator
```

Runs, with `sed 's/=\(.*\)$/_0=\1/'` applied to the conf so the FASED driver sees `+mm_*_0=`:

```bash
# HyperRAM, fixed latency. Result: exit 0, 10000 HYPERREQ lines.
./VAXI4Fuzzer +permissive $(sed 's/=\(.*\)$/_0=\1/' \
  /scratch/trazzaque/memory-peripherals/configs/hyperram-200-fixed.conf | tr '\n' ' ') +permissive-off
# RPC, open page, speed-1600. Result: exit 0, 10000 RPCREQ lines.
./VAXI4Fuzzer +permissive $(sed 's/=\(.*\)$/_0=\1/' \
  /scratch/trazzaque/memory-peripherals/configs/rpcdram-1600-open.conf | tr '\n' ' ') +permissive-off
```

The binaries live under `third_party/firesim/sim/generated-src/f2/`. Full logs are `results/logs/hyperram-fuzzer-run.log` and `rpc-fuzzer-run.log` (large; the fuzzer also prints every byte). Short extracts are `hyperram-trace-sample.txt` and `rpc-trace-sample.txt`.

The first HyperRAM requests are a read at cycle 524390 and a write at 524418. The gap is 28 CK: 3 of command, 14 of fixed latency, 4 of data (8 B at 2 B/CK), and tRWR of 7. The next read is 23 CK later (same transfer plus tCSHI of 2). The latency column is 14 on every line. Address `0x212e40` is reported as row `0x84b`, which is that address divided by 1024.

The RPC line for `0x212e40` is bank 0, row `0x425`, which is `addr[22:11]`. The fuzzer only has 22 address bits, so bank 1 is never selected. Python `test_four_banks_are_independent_above_bit_23` covers that map.

Open-page Chisel column commands in `results/logs/rpc-fuzzer-refresh.log` are 8 CK apart (`524402`, `524410`, `524418`), which is one RPC word-time, overlapping the data burst. That run also programmed `tREFI=4000` and `tRFC=80` and printed 237 `RPCREF` lines, 4080 CK apart (`tREFI + tRFC`). Exit 0.

## ETH command FSM

```bash
cd /scratch/trazzaque/memory-peripherals/rtl
# see results/logs/rtl_eth_fsm_build.log for the verilator file list
./obj_fsm/Vtb_fsm
```

Result: **PASS**, `results/logs/rtl_eth_fsm.txt`. The unmodified `rpc_cmd_fsm` emitted closed-page ACT, then RD or WR, then PRE. `phy_ready` was tied high, so the commands are one cycle apart. `rpc_timing_fsm` is what inserts tRCD; it is not in this bench. `rpc.sv` and the PHY were not elaborated.

## Not run

- Any FPGA, XDMA, or physical memory run.
