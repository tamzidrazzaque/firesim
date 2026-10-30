# Independent EM6GA16L timing model

This document records the 2026-10-25 run. The 2026-10-28 SV handoff and
current results are in `SV_VERIFICATION_HANDOFF.md` and the top of `STATUS.md`.
The old N_REF=2 negative result below is now an intentional regression test;
the legal ETH configuration programs row-step waits for one through four
banks. The active-state command grid discovered in Rev. 1.4 section 2.8 is
now enforced by the Python checker, SV observer, and independent FASED
scheduler.

The speed-1600 command model was written from Etron EM6GA16L Rev. 1.4
([official PDF](https://etron.com/wp-content/uploads/2022/04/EM6GA16LGDBXCAEA-RPC1-DRAM-Induatrial_Rev.-1.4.pdf)) and
`independent/FASED_CONTRACT.md`. That generation did not receive the ETH
controller, the existing `src/memperiph/rpcdram.py` model, or the earlier
controller patches. It is not a clean-room result: this session had already
read the ETH RTL before that split, and the clock-profile and pin-packet
code below was added afterward in this same session. The speed-1600 tests
were re-run after those edits and still pass.

## What the isolated model checks

`independent/rpc_fased/` issues one command at the cycle the caller offers.
An early command appends a violation and does not change bank or array
state. It is not given a later cycle.

| Parameter | Cycles at 1.25 ns | Source |
|---|---|---|
| tRCD, tRP | 11 | 13.75 ns, Table 11-3 |
| tRAS | 28 | 35 ns, Table 11-3 |
| tRC | 39 | 48.75 ns, Table 11-3 |
| tRRD | 6 | 7.5 ns, Table 11-3 |
| tWR | 12 | 15 ns, Table 11-3 |
| RL, WL | 12 | AL=1, CL=11, WL=RL, Table 7-2 |
| One WORD | 8 | 32 bytes, BL16, Section 2.4. BC=0 is one WORD |
| tPPD | 4 idle, 8 active | Table 11-3 |
| One-shot refresh busy | 80 | one tREFI, 100 ns. No tRFC is specified |

`issue()` records tRCD, tRP, tRAS, tRC, tRRD, tWR, nWR, tWTR, tRTW, tPPD,
WORD occupancy, tMOD, tMRD, reset, ZQ, and the Section 4 order
reset, then precharge-all, then MRS.

## Later edits, and why they are not part of the isolated drop

`profiles.py` converts the same nanosecond minima with `ceil(ps / tCK)` and
leaves tCK-counted minima in cycles. At 5 ns that is tRCD=3, tRP=3, tRAS=7,
tRC=10, tRRD=2, tWR=3, tREFI busy=20, tPPD still 4 and 8. RL follows the CL
in the MRS packet. Table 11-3 lists a minimum tCK per CL and no maximum, so
CL=8 at 5 ns is accepted. `device.py` reads timings from `self.p`, which
defaults to the speed-1600 column. MRS is placed at `max(tRP, tPPD)`; at
1.25 ns that is still tRP.

## ETH interface

FASED's AXI model chooses its own ACT and CAS times. It cannot see a command
the ETH controller already emitted, and it must not be inserted in a way
that delays an illegal command until it becomes legal.

The check that was run is a command observer. `rtl/rpc_pin_memory.sv` prints
`RPC_PIN_CMD` when a parallel packet is assembled. `packets.py` decodes that
word from Tables 7-1, 7-2, and 7-4. `check.py` calls `RpcDram.issue` at the
printed cycle. The functional bytes still come from the pin model. The
checker does not supply data and does not reschedule.

The controller under test is the existing `rpc_synth_wrap` RTL. The 200 MHz
traces were not regenerated. The checker reads:

- `results/logs/eth_full_pin_run.log` (21 commands)
- `results/logs/chipyard_eth_rocket_stdout.log` (394)
- `results/logs/chipyard_eth_boom_stdout.log` (409)

## Result

824 commands, 0 violations, at tCK=5 ns and the MRS the controller sent
(CL=8, nWR=4, Zout=120 ohm). Rocket and BOOM each activate banks 0, 1, 2,
and 3. Both cores reach the `TestDriver` success branch, which is the
workload's own compare of 64 words on each bank (`workloads/rpc_banks.c`).
Report: `results/logs/eth_independent_timing.txt`.

Every data access in those traces is closed-page: ACT, one READ or WRITE,
PRE. ACT-to-CAS is 16 CK. CAS-to-PRE is 48 CK on the core traces (40 or 48
on the short bench). Sixteen CK is 80 ns, which clears tRCD (13.75 ns) and
active tPPD (40 ns). The traces do not sit on those minima. They contain no
REFRESH, no second column to an open row, and no back-to-back column
commands inside one tRTW.

The pin model itself only fatals on tRCD, tRP, and tRAS of 3, 3, and 7
cycles, plus init order. The independent checker also applies tPPD, tRRD,
tWR, tRC, tRTW, tWTR, and refresh. The traces pass those too.

## Negative tests

Injecting an earlier cycle into the standalone trace, without moving the
following commands, is reported and not repaired:

| Injection | Constraint | Earliest legal cycle |
|---|---|---|
| First column moved to ACT+tRCD-1 | tRCD and tPPD | ACT+tRCD, and ACT+8 while the row is open |
| PRE inserted at ACT+tRAS-1 | tRAS | ACT+tRAS |
| WRITE inserted at READ+tRTW-1 | tRTW | READ+8 at CL=8 |
| ACT one cycle after an otherwise legal REF | tREFI | REF+20 at 5 ns |

`independent/tests_eth_check.py` covers these. The speed-1600 suite,
including the refresh readings, is 29 tests.

## FASED simulation

The earlier plusarg run of the original `RpcDramModel` binary is still
`results/logs/rpc-independent-fuzzer-summary.txt`. That binary's refresh
stall is a single register. The separate Chisel class is below.

The run exited 0 with 10,000 `RPCREQ` lines and 6,454 `RPCREF` lines.
Minimum refresh spacing is 160 CK. 3,294 gaps are exactly 160. The others
are longer because refresh starts only from the scheduler's idle state.
568 successive column commands are 8 CK apart. Summary:
`results/logs/rpc-independent-fuzzer-summary.txt`.

`*** PASSED ***` in that log means the fuzzer raised `finished`.
`AXI4Fuzzer` ties `error` to 0, so the line is not a data compare.

## Where the two Python models disagree

| Topic | Original `src/memperiph/rpcdram.py` | Independent model | Resolution |
|---|---|---|---|
| Refresh busy | 4096 rows × tREFI × selected banks | `row_step` uses that product. `one_trefi` keeps the earlier one-period window | Section 5 says one command burst-refreshes the selected banks and that tREFI is the period on entry. It does not print tRFC. The >85 °C note allows one or two banks in LP mode and not four, which matches the product against the 32 ms hot limit (13.1 ms, 26.2 ms, 52.4 ms). The sentence "four banks take 64 ms" matches the retention window, not 52.4 ms. Both readings stay selectable. `row_step` is the one used for the controller check. |
| BC field | n_words = BC+1, citing the datasheet and the ETH FSM | n_words = BC+1 from Section 2.4 | They agree. The independent reading does not need the controller. |
| Host address | ETH `rpc_cmd_fsm` map | No host map. The checker uses BA/RA/CA from the packet | The datasheet does not define a CPU physical address. |
| 200 MHz CL | `profile_200mhz()` now uses CL=8, RL=9, tRTW=8 | The MRS packet is CL=8, so RL=9 and tRTW=8 | The packet is what the DRAM sees. The former CL=3 profile under-checked turnaround. |
| nWR | precharge uses tWR and does not reject a short MRS code | nWR must be at least tWR in cycles | At 5 ns, tWR is 3 and the controller's nWR=4 is legal. At 1.25 ns the Table 7-2 default of 8 is short of 12. |
| Idle PRE | no-op, so init PRE ALL works | legal for the Section 4 precharge-all; a later PRE of an idle bank is an error | The traces' later PREs target the open bank, so both accept them. |
| Read to PRE | end of the read data | same, named `read_to_precharge` | Table 11-3 has no tRTP. |

## Refresh

Section 5 calls one-shot fast refresh a burst refresh of the selected banks, with tREFI equal to 100 ns on entry. DQS and DQS# go high while the device is busy. tRFQSd (300 ns, 3×tREFI) is the maximum latency from the REF command until DQS goes high, not the length of the busy window. Figures 5-1 and 6-7 say the device exits after one loop of the selected banks.

The cycle count of that loop is not in Table 11-3. Two readings are implemented:

| Reading | One-shot busy window | 1 bank, FST, 1.25 ns | 4 banks, FST, 1.25 ns | 4 banks, FST, 5 ns |
|---|---|---|---|---|
| `one_trefi` | one tREFI | 80 | 80 | 20 |
| `row_step` | rows × tREFI × banks | 327,680 | 1,310,720 | 327,680 |

LP four-bank `row_step` is 52.429 ms. One bank is 13.107 ms and two banks are 26.214 ms, both under the 32 ms hot retention limit. Three and four banks are over it. That is the same restriction as the Section 5 note. The 64 ms sentence is the retention interval, not an exact product.

Loop mode still blocks until the exit pulse. The datasheet then says the device finishes the current loop, without a number. `loop_finish="unspecified"` adds nothing after tCKSPX. `loop_finish="row_step"` adds one inferred pass. The default device remains `one_trefi` so the original 24 tests still pass. Five more tests cover both readings. Commands during the window are rejected. A command on the exact end cycle is accepted.

## Directed ETH controller run

`scripts/run_eth_timing_directed.sh` runs the production `rpc_synth_wrap` with `rpc_pin_memory` and `rpc_timing_observe` on the same pins. The observer has no ready output. Log: `results/logs/eth_timing_directed_run.log`.

Init, repeated reads of one address, writes and reads of banks 0–3, a write followed by a read, and an 8-beat burst produced 60 pin commands and 0 observer violations. ACT-to-CAS was 16 cycles on all 21 column commands in that section. Every data access was ACT, one column command, PRE. The command FSM has no open-page path: it precharges after the column command. A second column to an open row is not something this controller emits.

The 8-beat write is one CAS with burst count 1 (two 32-byte words). That is the controller's burst. It does not emit a separate serial-streaming command.

Direct REF commands, with the testbench's N_REF registers left at 2, were followed by ACT 16 cycles later:

| Banks | Pin gap | `one_trefi` legal at | `row_step` legal at |
|---|---|---|---|
| 1 | 16 | REF+20 | REF+81,920 |
| 2 | 16 | REF+20 | REF+163,840 |
| 4 | 16 | REF+20 | REF+327,680 |

The Python replay and the online observer agree: 17 `tREFI` violations under `row_step`. Under `one_trefi` the ACT 16 cycles after each REF is also early (3 violations, plus the RD and PRE that follow a rejected ACT). The controller was not stalled. The pin model still returned data.

`rpc_timing_fsm` waits `n_ref_1` through `n_ref_4` cycles, chosen by the bank-mask popcount. It does not compute rows × tREFI. Programming `n_ref_4` to 327,680 produced the next ACT 327,696 cycles after the four-bank REF. That command is legal for `row_step`. The controller can wait. The value in the register is what it waits, and the testbench's 2 is below both readings.

## Independent FASED model

`fased/scala/midas/models/dram/IndRpcDramModel.scala` is a separate Chisel class. `RpcDramModel.scala` is unchanged. The new model was compiled with:

```bash
make TARGET_PROJECT=fasedtests TARGET_CONFIG=DefaultConfig \
  PLATFORM_CONFIG=IndRpcDramF2ReqTraceConfig verilator
```

`configs/indrpc-1600-open.conf` disables refresh. The run exited 0 after
959,581 cycles. Replaying its `INDCMD` lines through the Python device
(`row_step`, speed-1600) accepted 28,623 commands and reported 0 violations:
9,312 ACT, 7,582 READ, 2,418 WRITE, 9,311 PRE.

`configs/indrpc-1600-refresh.conf` places one refresh at cycle 500,000.
The printed stall is 1,310,720, which is 4,096 × 80 × 4. The same replay
accepted that REF and the surrounding commands: 28,624 events, 0 violations.
The run exited 0 after 2,245,879 cycles.

The cycles are the model's tCK, one-to-one with the Python cycles. The
fuzzer's `PASSED` line is not a read-data compare. The 22-bit fuzzer address
does not reach the bank bits at [24:23].

The isolated FireSim copy needed `#include <cstdint>` in `cpu_managed_stream.h` before this g++ accepted the existing driver sources. That header change is not a timing-model change. The original `/scratch/trazzaque/firesim` tree was not edited.

## What is still open

Rocket was rebuilt with the observer in the harness
(`scripts/run_chipyard_eth_timing.sh rocket`). The workload reached the
`TestDriver` success branch. The observer saw 394 pin commands, banks 0–3,
ACT-to-CAS of 16 on all 130 column commands, no REF, and 0 violations.
Python replay of that log is also clean under both refresh readings, because
the trace never issues REF. Log:
`results/logs/chipyard_eth_timing_rocket_stdout.log`.

BOOM was rebuilt the same way. The workload reached the success branch.
The observer saw 409 pin commands, banks 0–3, ACT-to-CAS of 16 on all 135
column commands, no REF, and 0 violations. Log:
`results/logs/chipyard_eth_timing_boom_stdout.log`.

The workload still does not issue REF, an open-row second column, or a
read/write pair inside tRTW. Those gaps are in the directed controller run.
Physical RPC DRAM, the analog PHY, and the U250 were not used.
