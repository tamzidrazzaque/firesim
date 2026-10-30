# Memory-model validation status, 2026-10-30

The later ETH-command replay through the frozen specification checker is
`docs/SAGAR_INDEPENDENT_FASED_VALIDATION.md`. The matrix below is the
record of the earlier same-rule comparison and is unchanged.

This report separates the FireSim transaction schedulers, digital pin models,
the production ETH controller path, and physical hardware. The manufacturer
documents are [Etron EM6GA16L Rev. 1.4](https://etron.com/wp-content/uploads/2022/04/EM6GA16LGDBXCAEA-RPC1-DRAM-Induatrial_Rev.-1.4.pdf)
and [Infineon S80KS2562 Rev. *C](https://www.infineon.com/dgdl/Infineon-S80KS2562_1.8_V_256-Mb_HyperBus_Interface_HyperRAM_%28Self-Refresh_DRAM%29-DataSheet-v01_00-EN.pdf?fileId=8ac78c8c7dc4255f017dd82db3d308ae).
The exact supported modes, parameters, and open interpretations are in
`docs/SV_VERIFICATION_HANDOFF.md` and `docs/parameters.md`.

## Current matrix

| Layer or question | HyperRAM | RPC DRAM | Evidence or limit |
|---|---|---|---|
| Python functional/timing model | PASS, supported 200 MHz cases | PASS, original and separate independent checker | `tests/test_hyperram.py`, `tests/test_rpcdram.py`, `independent/rpc_fased/tests/`; full suite passed 2026-10-30 |
| FASED Chisel compile | PASS | PASS, original and independent class | Isolated FireSim `midas` compile passed 2026-10-29; `IndRpcDramModel` fuzzer binary built 2026-10-28 |
| FASED simulator | PARTIAL: 10,000 AXI fuzzer requests, no read-data compare | PASS for command scheduling: independent 1.25 ns and 5 ns traces replay without rule violations; no read-data compare | `results/logs/indrpc_spec_{open,refresh}.log`, `indrpc_200_closed{,_refresh}.log`; AXI fuzzer's `error` is tied low |
| Digital SV pin model | PASS for directed normal-mode cases | PASS for normal parallel packet data and timing observer | `results/logs/hyperram_pin_run.log`, `rpc_observer_run.log`, `eth_timing_directed_run.log` |
| Independent command checker | NOT APPLICABLE: separate HyperRAM Python model is a reference, not a clean independent derivation | PARTIAL: separate Python interpretation and replay; development session had prior ETH exposure | `docs/INDEPENDENT_RPC_TIMING.md` |
| Specification traceability | PARTIAL: normal-mode values and 1 KiB row checked; power and electrical modes unsupported | PARTIAL: Table 11-3 and packet modes checked; exact one-shot completion time unpublished | `docs/parameters.md`, `independent/rpc_fased/params.py` |
| Python/FASED/SV differential evidence | PARTIAL: FASED acceptance-gap comparison and SV directed latency tests; no single common pin trace through all three | PARTIAL: FASED command replay and ETH pin replay use the same independent rule engine at 5 ns; schedules differ | `scripts/compare_ind_fased.py`, `scripts/verify_rpc_trace_evidence.py` |
| Actual controller RTL | NOT RUN: no accessible HyperRAM controller integrated | PASS for ETH normal 200 MHz closed-page path and one read-backpressure case; PARTIAL for refresh and outstanding traffic | `rtl/tb_eth_timing_directed.sv`, `results/logs/eth_timing_directed_run.log` |
| Rocket and BOOM through ETH | NOT RUN | PASS: four-bank data workload and zero live observer violations; neither workload issues REF | `results/logs/chipyard_eth_timing_{rocket,boom}_stdout.log` |
| Negative timing tests | PASS: six expected pin violations | PASS: early packet and refresh violations detected without shifting offered cycles | `rtl/tb_hyperram_pin.sv`, `rtl/tb_rpc_timing_observe.sv`, `results/logs/eth_timing_directed_negative.log` |
| Refresh | PARTIAL: explicit injected collision; internal phase not published | PARTIAL: both one-tREFI and row-step readings remain selectable; direct BUSY signaling checked | Infineon section 6.3.2; Etron section 5; no measured completion waveform |
| Physical device | BLOCKED | BLOCKED | No board or device measurements were taken |

PASS refers only to the named supported mode and check. It does not imply
all-mode or electrical signoff.

## Independent FASED experiment and ETH comparison

The original speed-1600 Python command model was developed from Etron Rev.
1.4 and a generic FASED interface contract. The separate
`IndRpcDramModel.scala` schedules ACT, column, PRE, and REF using its runtime
parameters. The development session had previously inspected ETH RTL, and
the later 200 MHz profile, packet decoder, and controller replay were written
in that same session. The result **does not qualify as clean-room**. No fresh
isolated derivation was performed in this run. The address layout in the
FASED class also matches the ETH host map, although the packet checker reads
bank, row, and column directly from device packets.

An AXI FASED scheduler creates its own commands and can postpone them until
legal. It cannot judge when an external controller issued a command. The
comparison therefore uses a sideband Python checker on the observed
`RPC_PIN_CMD` stream. It preserves the original pin command cycle and never
feeds ready/backpressure to ETH. The SV observer watches the same pins and
also has no ready output. This is the strongest existing interface without
rewriting FASED as a command-input checker. The FASED class contributes
through its own `INDCMD` and `INDREF` command trace: the same independent
Python rules accept its emitted commands at both speed profiles, including
the 5 ns profile used for ETH. This is rule-set agreement, not equal command
schedules or direct FASED-to-ETH wiring.

| Trace | Clock/mode | Commands/events | Independent violations | Live SV violations |
|---|---|---:|---:|---:|
| Independent FASED open | 1.25 ns, CL=11 | 28,623 | 0 | not connected |
| Independent FASED refresh | 1.25 ns, CL=11 | 28,624, including 2 REF | 0 | not connected |
| Independent FASED closed | 5 ns, CL=8 | 30,000 | 0 | not connected |
| Independent FASED closed with REF | 5 ns, CL=8 | 30,001, including 1 REF | 0 | not connected |
| Standalone ETH full pin | 5 ns, CL=8 | 21 | 0 | not connected |
| ETH plus Rocket | 5 ns, CL=8 | 394 | 0 | 0 |
| ETH plus BOOM | 5 ns, CL=8 | 409 | 0 | 0 |
| ETH directed legal REF | 5 ns, CL=8 | 57, including 3 REF | 0 in either refresh reading | 0 |
| ETH deliberately short REF wait | 5 ns, CL=8 | 45, including 1 REF | 1 `tREFI` in either reading | 1 `tREFI` |
| ETH intermediate REF wait | 5 ns, CL=8 | 45, including 1 REF | 0 with one-tREFI; 1 `tREFI` with row-step | 1 `tREFI` with row-step |

In the 5 ns FASED closed-page trace, all 10,000 ACT-to-column gaps are 8 CK,
the first legal active-state packet slot. The observed ETH core traces use
16 CK. Both satisfy the independent `tRCD` and active-state 8-CK grid. They
do not demonstrate equality of controller scheduling policy. The FASED run
with refresh emitted `INDREF` at cycle 500,000 with a programmed 327,680-CK
four-bank stall. The AXI fuzzer success string only means it finished; its
read-data error signal is tied low. ETH data correctness instead comes from
the directed bench's explicit readback comparisons and the Rocket/BOOM
workload's four-bank comparisons. The directed ETH test also checked one
AXI read response's data, ID, last, and response stability across seven
cycles of R-channel backpressure.

`scripts/verify_rpc_trace_evidence.py` replays six saved pin logs under both
refresh readings. It checks command counts, exact row-step observer violation
cycle/earliest-legal-cycle agreement, and emits a raw-packet JSONL trace plus
SHA-256 hashes in `results/differential/rpc-traces/`. These exports are a
neutral handoff format for another independently built command checker. The
pin log does not contain write data, so replay validates timing and packet
fields, not stored bytes.

## Refresh conclusion

Etron section 5 says one-shot REF precharges all banks, refreshes the
selected banks, drives both DQS outputs high while BUSY, then pulses both low
and releases them. Table 11-3 gives tREFI (100 ns FST or 3.2 µs LP) and a
maximum entry-to-BUSY latency, but no exact one-shot tRFC. The row-step
reading computes 4,096 rows times tREFI times selected banks; it is an
inference, not a manufacturer-stated fixed completion time. The alternative
one-tREFI reading remains in the checker. A device BUSY waveform would
resolve which, if either, predicts completion.

With ETH `N_REF=2`, the measured next ACT was REF+16 CK. That violates even
the one-tREFI 20-CK reading at 5 ns, so this setting is demonstrably too
short for the two modeled interpretations. With `N_REF=20`, the measured gap
is REF+32 CK: the one-tREFI checker accepts it, while row-step rejects it.
The SV observer is configured for row-step and reports the same offered and
earliest legal cycle as that checker. This difference cannot determine which
wait the physical device requires. ETH `rpc_timing_fsm.sv` chooses
the programmed `n_ref_1` through `n_ref_4`; it does not derive a wait from
row count. The directed test programs 81,920, 163,840, and 327,680 cycles
for one, two, and four banks under the row-step interpretation. The next
ACTs then occur after BUSY and data reads back correctly. This demonstrates
a controller **configuration requirement**, while the exact silicon wait
still needs a vendor waveform or measurement. The isolated ETH copy has a
separate ACT-address patch; the refresh timing FSM is unchanged.

The directed test queues AXI reads after one- and two-bank REF and confirms
they return correct data after BUSY. It does not test sustained concurrent
traffic, several outstanding AXI IDs, or another ETH PHY clock. Rocket and
BOOM have no REF in their observed workloads. No claim is made for those
untested conditions.

## Scope of the models

HyperRAM SV: 200 MHz S80KS2562 Rev. *C normal mode, 32 MiB array,
48-bit DDR CA, CR0/CR1 and ID registers, fixed and variable latency,
explicit refresh collision injection, masks, wrap/linear addressing,
1 KiB rows, reset and CS# timing. The internal refresh phase is not
published. Hybrid sleep, deep power-down wake, retention loss, and analog
setup/hold are not implemented; the model must not be used to sign off those
features. The Python model's periodic refresh estimate and the SV model's
injected collision are different abstractions.

RPC SV: 200 MHz ETH CL=8 normal parallel packet path, four banks, 32-byte
words, first/last masks, digital DB/DQS behavior, one-shot REF BUSY, and
live command constraints. The checker also has speed-1600 Python and FASED
profiles. Serial streaming, loop refresh exit, power-down, deep power-down,
training, and analog timing remain unsupported. The production command FSM
emits ACT, one column command, then PRE; an open-page second column can be
tested in the independent model, but not claimed as ETH coverage.

## Reproduce the evidence

From this project directory, with the documented local toolchains and
isolated dependencies available:

```bash
./scripts/run_sv_spec_checks.sh --with-eth
./scripts/run_chipyard_eth_timing.sh rocket
./scripts/run_chipyard_eth_timing.sh boom
.venv/bin/python scripts/verify_rpc_trace_evidence.py
.venv/bin/python scripts/compare_ind_fased.py results/logs/indrpc_spec_open.log
.venv/bin/python scripts/compare_ind_fased.py results/logs/indrpc_spec_refresh.log
.venv/bin/python scripts/compare_ind_fased.py results/logs/indrpc_200_closed.log --tck-ps 5000 --cl 8 --page-policy closed
.venv/bin/python scripts/compare_ind_fased.py results/logs/indrpc_200_closed_refresh.log --tck-ps 5000 --cl 8 --page-policy closed
```

The 5 ns FASED runs use the built `IndRpcDramF2ReqTraceConfig` fuzzer binary
with `configs/indrpc-200-closed.conf` and
`configs/indrpc-200-closed-refresh.conf`. Add `_0` to each `+mm_*` name
before the equals sign, as for the existing 1.25 ns runs. Preserve the raw
logs; the JSON report includes their hashes. Generated logs and dependency
checkouts are outside the source commit.

## Next comparisons

Give Anoushka the exported raw packet, cycle, bank, row, column, burst count,
and REF fields. Compare accepted/rejected commands and earliest legal cycles
without altering the timestamps. Investigate any disagreement against the
manufacturer tables before changing either implementation. A fresh isolated
derivation could improve independence, but the current work must keep its
provenance label. Device BUSY waveforms and physical memory tests are needed
to establish the exact one-shot completion behavior, retention, and PHY
electrical margins.
