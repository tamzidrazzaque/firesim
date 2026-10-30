# Original RPC model: what came from the datasheet, and what did not

This note records the original implementation audit. Since that audit,
`src/memperiph/rpcdram.py` has been corrected to enforce the active-state
eight-CK parallel-command grid, and the observed ETH MRS is CL=8/RL=9.
`rtl/rpc_timing_observe.sv` is the current pin-path timing checker; see
`SV_VERIFICATION_HANDOFF.md`. The historical limitations below apply to the
older pin-model-only runs.

This note is about `src/memperiph/rpcdram.py` and
`fased/scala/midas/models/dram/RpcDramModel.scala`. It is not a claim that
those files are a clean-room specification model. They were written in a
session that also read the ETH Zurich controller.

An isolated reimplementation lives under `independent/`. That tree was given
only the Etron Rev. 1.4 PDF and a generic command-checker contract.

## Specified in Etron Rev. 1.4 and implemented that way

| Behavior | Datasheet | Original model |
|---|---|---|
| 4 banks, 4096 rows, 2 KB page, x16 | Table 1-2 | `n_banks`, `n_rows`, `page_bytes` |
| 32-byte minimum word, 8 CK on the data bus | Fig. 2-14, BL16 | `word_bytes=32`, `burst_ck_per_word=8` |
| Speed-1600 tCK 1.25 ns, CL 11 | Table 11-3 | `profile_1600` |
| tRCD, tRP 13.75 ns; tRAS 35 ns; tRC 48.75 ns; tRRD 7.5 ns; tWR 15 ns | Table 11-3 | ceil to CK |
| RL = AL + CL, AL fixed at 1, WL = RL | Table 7-2 | `rl_ck` |
| tPPD 4 CK idle, 8 CK with a row open | Table 11-3 | `tPPD_idle_ck`, `tPPD_act_ck` |
| tMOD max(12 CK, 15 ns) | Table 11-3 | `tMOD_ck` |
| Power-up 200 µs clocks, 5 µs reset, then PRE, MRS, ZQ | Section 4 | `initialize()` |
| One-shot refresh walks selected banks | Section 5, Table 7-5 | duration `n_rows * tREFI * n_banks` |
| PRE of an already idle bank is a no-op (init PRE ALL) | Section 4 | no `pre-closed` violation |
| Early ACT/RD/PRE recorded, not silently delayed | contract of `issue()` | violations `tRCD`, `tRAS/tWR`, `tRP/tRC`, `tRRD`, `busy` |

## Not from the datasheet alone

| Behavior | Where it came from | Consequence |
|---|---|---|
| Host byte map `addr[24:23]=bank`, `[22:11]=row`, `[10:5]=column group` | ETH `rpc_cmd_fsm.sv` ACT/RD packing. The datasheet defines BA/RA/CA, not a host physical address. | Matching ETH bank numbers is not a spec result. |
| Burst field means `n_words - 1` | ETH `rpc_timing_fsm.sv` countdown `(BC<<3)+7`, and a LiteDRAM comment. Table 7-3 lists the field as 0..63. | A spec-only reading can disagree. |
| 200 MHz profile | ETH PHY `CLOCK_PERIOD=5` and observed MRS CL=8 | The corrected profile uses CL=8, RL=9, tRTW=tWTR=8 CK. The earlier CL=3 assumption was wrong for this ETH trace. |
| Closed-page default in the ETH integration | ETH FSM precharges after every CAS | The spec allows the row to stay open. |
| No tRTP number; precharge waits until the read burst ends | Table 11-3 has no tRTP | Inference, labeled as such. |
| Parallel-packet bit positions checked against LiteDRAM | `encode_parallel` | Useful, but not datasheet-only. |

## What the existing pin model actually enforces

`rtl/rpc_pin_memory.sv` is a functional device with a few cycle checks at the
200 MHz numbers used by the ETH testbench: tRCD 3, tRP 3, tRAS 7, ZQINIT 400
cycles, and the reset/PRE/MRS order. It does not check tRRD, tPPD, tWR,
tRC, or a full-array refresh. A workload that passes that model has not been
shown to meet every row in Table 11-3.

`AXI4Fuzzer` still ties `error` to 0. A FASED fuzzer exit does not prove
read data.

## FASED versus the controller

The Chisel `RpcDramModel` sits on AXI. It turns a burst into its own ACT/CAS
schedule. It never sees the commands ETH emitted. Replacing Chipyard's memory
port with that model checks the core and the AXI fabric. It does not check
the controller.

The pin-path runs (`scripts/run_chipyard_eth_pin.sh`) do run ETH, and the
pin model checks the short 200 MHz inequalities above. They are not the
independent checker described in `independent/`.
