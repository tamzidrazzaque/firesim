# Status

## 2026-10-28 SV verification baseline

The current handoff is `docs/SV_VERIFICATION_HANDOFF.md`. The HyperRAM
S80KS2562 digital pin model and Etron EM6GA16L RPC pin memory/timing observer
have standalone positive and negative tests. RPC active-state parallel
commands now obey the datasheet's eight-CK **grid**, including at speed-1600
where tRCD=11 CK requires ACT-to-CAS=16 CK. The ETH observer checks REF
against ACT, read, write, and precharge recovery and rejects commands during
BUSY. The RPC pin memory drives both DQS pins high during BUSY, pulses both
low on completion, and exposes drive enable. The HyperRAM model covers
fixed/variable latency, forced refresh collision, registers, masks, reset,
CS# timing, wrap, and 32 MiB geometry.

`./scripts/run_sv_spec_checks.sh` passes the standalone SV and Python suites.
`./scripts/run_eth_timing_directed.sh` passes 1-, 2-, and 4-bank row-step REF
with readback, and its underprogrammed REF negative run reports `tREFI`.
The rebuilt independent FireSim model compiled and its open-page fuzzer trace
replayed 28,623 commands with zero Python checker violations. Its
refresh-enabled trace replayed 28,624 events, including two one-shot REF
commands, also with zero violations.
Rocket and BOOM were rebuilt with the fatal observer and reached the workload
success branch: Rocket emitted 394 pin commands, BOOM 409, each across banks
0–3 with zero observer violations. Logs are
`results/logs/chipyard_eth_timing_{rocket,boom}_stdout.log`. Neither workload
issued REF; the directed test does. The exact one-shot REF busy duration is not published by
Etron, so row-step remains an explicit interpretation; both variants are
selectable. This is a digital normal-mode baseline, not all-mode/electrical
signoff. The dated entries below record earlier runs and assumptions.

## 2026-10-25 Independent RPC timing check

The speed-1600 model in `independent/rpc_fased/` was generated from the Etron
Rev. 1.4 PDF only. This session had already read the ETH controller, so the
result is not claimed as clean-room. A 5 ns profile and a pin-packet replay
were added afterward. Details and the disagreement table are in
`docs/INDEPENDENT_RPC_TIMING.md`.

The ETH RTL was not modified. Its printed `RPC_PIN_CMD` timestamps were
replayed. An early command is reported and is not delayed.

| Trace | Commands | Violations | Banks | Data |
|---|---|---|---|---|
| Standalone ETH pin bench | 21 | 0 | 0 | AXI readback checked by the bench |
| Rocket `rpc_banks` through ETH and the pin model | 394 | 0 | 0–3 | `TestDriver` success branch |
| BOOM, same workload and path | 409 | 0 | 0–3 | same |

Those accesses are closed-page ACT / one column / PRE. ACT-to-CAS is 16 CK
and CAS-to-PRE is 48 CK on the core traces. There is no REF and no row hit.
Negative injections of an early column, an early PRE, an early write after a
read, and an ACT during refresh are each reported by name.

The directed RTL run is `results/logs/eth_timing_directed_run.log`. With
N_REF left at 2, ACT follows REF by 16 cycles. That is early for one tREFI
(20 cycles at 5 ns) and for the row-step window. Programming `n_ref_4` to
327,680 makes the next ACT legal. The controller RTL was not changed.

`IndRpcDramModel` compiled as its own FASED binary. Its open-page trace
replays through the Python device with 0 violations on 28,623 commands.

| Validation level | Original model | Independent model | ETH integration |
|---|---|---|---|
| Specification-derived timing | PARTIAL. Core nanosecond minima are from Table 11-3. The host map and the 200 MHz CL=3 profile are not. | PASS for the speed-1600 command rules. Two refresh readings are documented. `row_step` is the one used against the controller. | FAIL for refresh when N_REF is 2. PASS for the closed-page commands in the 824-command traces. |
| Python unit tests | PASS. `results/logs/pytest.txt`, 32 tests | PASS. 29 speed-1600 tests, plus 9 replay tests | PASS on traces with no REF. FAIL on the directed REF trace |
| Chisel compilation | PASS. Existing `RpcDramModel` | PASS. `IndRpcDramModel` | n/a |
| FASED Verilator simulation | PASS. 10,000 requests. Fuzzer `error` is tied to 0 | PASS. New binary, open-page run, 0 Python disagreements. Fuzzer `error` is tied to 0 | NOT RUN. FASED does not see ETH pin commands |
| Command-level timing validation | PASS in the original Python device | PASS, including rejection of early commands | FAIL on refresh spacing. The observer does not move the early ACT |
| PHY/pin-side functional simulation | n/a | n/a | PASS. Digital `rpc_pin_memory.sv`. Not analog |
| Rocket end-to-end | PASS on the FASED memory port, a different configuration | NOT RUN through FASED | PASS. Live observer, 394 commands, 0 violations. The workload issues no REF |
| BOOM end-to-end | PASS on the FASED memory port | NOT RUN through FASED | PASS. Live observer, 409 commands, 0 violations. The workload issues no REF |
| Physical hardware | NOT RUN | NOT RUN | NOT RUN |

## 2026-10-23 ETH pin path with Rocket and BOOM

**PASS in Verilator:** `rpc_synth_wrap` runs its AXI interface, command FSM,
timing FSM, PHY, and external DB/DQS/STB pins against `rtl/rpc_pin_memory.sv`.
The Etron [EM6GA16L Rev. 1.4 datasheet](https://etron.com/wp-content/uploads/2022/04/EM6GA16LGDBXCAEA-RPC1-DRAM-Induatrial_Rev.-1.4.pdf)
sets the 32-byte word, eight-cycle transfer, active-low byte masks, CL/AL,
and tRCD/tRP/tRAS used by the test. This is a digital pin model; analog signal
integrity and board timing are outside the simulation.

| Test | Result | Evidence |
|---|---|---|
| Full ETH standalone | PASS: 8-byte write/read, partial four-byte overwrite preserving other bytes, 64-byte AXI burst | `results/logs/eth_full_pin_run.log`, `rtl/tb_eth_full_pin.sv` |
| Chipyard Rocket → ETH RTL → pin memory | PASS: `rpc_banks.riscv` returned success; pin commands and reads reach banks 0–3 | `results/logs/chipyard_eth_rocket_stdout.log`; `scripts/run_chipyard_eth_pin.sh rocket` |
| Chipyard BOOM → ETH RTL → pin memory | PASS: same workload and four-bank reads | `results/logs/chipyard_eth_boom_stdout.log`; `scripts/run_chipyard_eth_pin.sh boom` |

Chipyard's AXI memory port sets CACHE[1]=0. ETH's existing 64-to-256-bit
upsizer converts burst length only when CACHE[1]=1. The harness wrapper sets
that normal-DRAM modifiable bit. Without it, the Rocket workload failed:
an eight-beat 64-byte request became eight 32-byte RPC words and later stores
zeroed earlier data. The failing trace and diagnosis are reproducible from the
controller's `axi_dw_upsizer.sv` and the successful logs after the bridge fix.
`integration/chipyard/` holds the harness sources; setup copies them into the
isolated Chipyard checkout. The original Chipyard tree is untouched.

This run does not use FASED for memory data. It does not validate an FPGA,
analog PHY, refresh during a long workload, or all Etron timing corners.

## 2026-10-23 integration update

| Path | Result | Evidence and boundary |
|---|---|---|
| ETH `rpc_interface` AXI data path + `rpc_cmd_fsm` + transaction-side 256-bit memory | **PASS**: 64-bit writes, masked writes, readback, AXI IDs, and ACT/CAS/PRE on banks 0–3 | `results/logs/eth_interface_data.log`; `rtl/tb_eth_interface_data.sv`. The bench substitutes a behavioral memory at the controller's transaction side. It does not exercise `rpc_timing_fsm`, PHY pins, or a physical RPC DRAM. |
| ETH full `rpc_synth_wrap` | Verilator lint/elaboration **PASS** | `results/logs/eth_full_top_lint.log`; this is not a transaction test. |
| Chipyard Rocket + RPC FASED model | **PASS**: bank write/read workload, 10,882 target cycles; request trace includes banks 0–3 | `results/logs/rocket_rpc_target.out`; model is connected to the Chipyard memory port directly. |
| Chipyard BOOM + RPC FASED model | **PASS**: same workload, 6,274 target cycles | `results/logs/boom_rpc_target.out`; same connection as Rocket. |

The four rows above describe the earlier FASED and transaction-side checks.
The new pin-path runs are reported in the section above.

The initial core runs stalled because `+mm_readMaxReqs=32` and `+mm_writeMaxReqs=32` exceeded the generated Chipyard FASED capacity of 10; the four-bit runtime registers stored zero. Both RPC config files now set 10. The ETH four-bank bench also caught and fixed the first ACT using stale `addr_q`; the isolated controller patch is in `patches/eth_rpc_cmd_fsm_act_addr.patch`.

Checked 2026-10-16. “Tests passed” means the Python suite or the named Verilator bench, not an FPGA run.

| Component | Implemented | Compiles | Tests passed | Integrated | Limitations |
|---|---|---|---|---|---|
| HyperRAM device + FASED scheduler (Python) | Yes | Yes (pytest) | Yes, including tCSM split and ID0 | Scheduler drives the device | Not a pin PHY. Row size inferred. Default tCSM is the ≤85 °C column (4 µs) |
| HyperRAM transaction RTL | Yes | Yes, Verilator 5.022 | Yes, `rtl/obj_hyper/Vtb_hyperram` | Testbench only | 256-byte array, fixed latency, one byte per request |
| HyperRAM Chisel FASED model | Yes | Yes. Scala compile and Verilator of the AXI fuzzer | Fuzzer exited 0. 10,000 `HYPERREQ` lines, fixed latency 14 CK | `HyperRAMF2ReqTraceConfig` on the FASED bridge | Refresh collision is a period counter, not the Python row-debt integral |
| RPC DRAM device + scheduler (Python) | Yes | Yes | Yes, 11 tests in `tests/test_rpcdram.py` | Scheduler’s commands are checked by the device | Serial utilities other than BST are not generated. PHY analog timing is absent |
| RPC command-level RTL | Yes | Yes, Verilator | Yes, `rtl/obj_rpc/Vtb_rpc` | Testbench only | One byte per bank, not a 32-byte burst or DQS |
| ETH `rpc_cmd_fsm` | Their RTL plus `common_cells` v1.21.0 | Yes, Verilator | Yes, `results/logs/rtl_eth_fsm.txt` | Closed-page ACT then CAS then PRE for a read and a write | `phy_ready` tied high. `rpc_timing_fsm`, the PHY, and `rpc.sv` are not in this bench, so tRCD is not applied |
| RPC Chisel FASED model | Yes | Yes. Rebuilt after the open-page change | Fuzzer exit 0, 10,000 `RPCREQ`. A second run with `tREFI=4000`, `tRFC=80` exit 0 and 237 `RPCREF` lines | Open-page column commands are 8 CK apart | No serial ACT to a second bank during a burst. 22-bit fuzzer stays in bank 0. Full 1.638 ms refresh is plusarg-selectable, not the smoke default |
| Calibration harness | Yes | Yes | Yes, synthetic recovery of L=7 and RL=12 | Reads traces the model produced | Not fitted to silicon |
| Safe-probe / agent harness | Yes | Yes | Yes, legal plan passes, illegal RD fails | JSON in, JSON out | Allow-list is not an electrical limit |
| Characterization | Yes | n/a | Script completed | Python models | Modeled cycles only. See `results/characterization/` |
| U250 / physical memory | No | n/a | Not run | Not connected | No XDMA, JTAG, or programming in this run |

## Comparison

| Check | HyperRAM | RPC DRAM |
|---|---|---|
| Python functional and timing | PASS. ID0 is `0x0E86`. A 2 KiB read is split so no chip-select exceeds tCSM | PASS. Four banks at bit 23 are independent. Refresh stall is 1,310,720 CK |
| Chisel FASED | PASS. 10,000 fuzzer requests, exit 0. Accept deltas match the formula | PASS. 10,000 requests, exit 0. Open-page commands 8 CK apart. 237 refresh stalls in the short-tRFC run |
| Differential | `results/differential/hyperram.txt`, 0 mismatches | Row `0x425` for address `0x212e40` matches `addr[22:11]` |
| Protocol | Transaction level. Not the DQ/RWDS pins | Python command checks. Not DQS |
| Controller RTL | None available (private repo unreachable) | `rpc_cmd_fsm` ACT/CAS/PRE PASS. Timing FSM and PHY not simulated |
| End-to-end data | Python shadow memory. Fuzzer `error` is tied to 0 | Same |
| Physical | None | None |

## Evidence

- Python: `results/logs/pytest.txt` — 26 passed.
- Chisel: `results/logs/midas-compile.log` (`[success]`, 67 s) and `results/logs/firesim-compile.log` (`[success]`, 9 s). A second midas compile after a cleanup is `results/logs/midas-compile-2.log`.
- RTL: `results/logs/rtl_hyperram.txt`, `rtl_rpc.txt`, `rtl_eth_decoder.txt`.
- Numbers: `results/characterization/performance.csv`.

## Levels, in the sense of the task

| | HyperRAM | RPC DRAM |
|---|---|---|
| Implemented | Device, FASED scheduler, Chisel timing model, small RTL | Device, scheduler, Chisel timing model, small RTL, ETH decoder hook |
| Compiles | Python, Verilator bench, Chisel (`midas` and `firesim`) | Same |
| Unit tested | Yes | Yes |
| Protocol validated | HyperBus transaction rules and tCSM in Python. Not DQ/RWDS pins | ACT/PRE/CAS/REF legality in Python. ETH command-word decode in Verilator. Not DQS pins |
| Integrated | FASED bridge elaborates `HyperRAM transaction timing model` and the fuzzer’s AXI port feeds it | Same for `RPC DRAM bank timing model`, plus the ETH decoder is instantiated |
| End-to-end validated | 10,000 fuzzer requests, exit 0. Deltas match the Chisel formula (read-to-write 28 CK). `error` is tied to 0, and TLRAMModel still prints undefined gets, so this is not a data-compare | 10,000 requests, exit 0, plus a refresh run. Same `error` tie-off |
| FPGA validated | No | No |

FireSim checkout used for the compile is the isolated tree at `third_party/firesim`, content from `hbm-arch1-compact-test` commit `8ce47277fe9d38dfd0f73dd94ea15b16793c6878`, with `fased/` applied on top. The original `/scratch/trazzaque/firesim` working tree was not edited.
