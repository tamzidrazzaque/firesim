# Sagar independent FASED validation

This report answers whether a specification-derived RPC DRAM timing
checker, built without the ETH Zurich controller, can judge commands
that the controller actually issued. The checker is
`rpc.RpcTimingChecker` in `independent/cleanroom/`. Replay is offline:
each observed pin command is offered at its original cycle. The Chisel
module decides. It does not delay an early command into a legal slot.

The earlier Python checker and `IndRpcDramModel` remain in the tree.
They are a different derivation. Their results are the comparison
baseline, not this experiment.

## A. Was a genuinely clean-room model created?

Yes, with the limits below.

A separate Cursor agent session
(`bfa1afa5-1b33-45d9-ad77-b8c613a81ca4`, Claude Opus 5.5 extra-high)
ran under Linux Landlock ABI 4. Its filesystem allowlist was the
workspace, the agent binary, and generic system libraries. A probe in
that policy could not open this repository, the ETH RTL, or prior
transcripts, including through `/proc/self/root`. The session
transcript contains no path outside the workspace and no mention of
ETH. Codex was tried first and stopped with a quota error, so it did
not produce the model. User namespaces and Docker were not available.

Landlock on this kernel does not mediate `stat`, so a guessed path can
reveal that a file exists. Connect was logged rather than blocked by
address. The log shows HTTPS to the agent API and a Cloudflare
address, not a fetch of controller sources.

Permitted inputs were Etron EM6GA16L Rev. 1.4 (SHA-256
`c04a6b4192570c7b165efeeee0b3a8d2ee58c69c66609d5272103d2b517741cc`),
a controller-neutral command contract, a fictional spacing example, and
Chisel 3.6.0 on JDK 11. The Scala sources hash to
`766dc95fe44bf909c9cf761f7d1ea5c9aa18dd7c6d9f5d22281dc23f749d2823`.
The kept tree, including the datasheet and the agent's notes, hashes to
`1c22e161c534d98a9b1a86d6f09f5c51b72c5a41d4e99842026a255f7860196c`.
Details are in `independent/cleanroom/PROVENANCE.md`.

The checker was not edited after these hashes, including where its
refresh result disagrees with ETH and with the older checker.

## B. Does the Chisel checker evaluate ETH commands?

Yes. The path is a replay, not a second Python ruleset and not FASED
scheduling its own commands.

`rpc_pin_memory` prints `RPC_PIN_CMD` with the cycle and the 32-bit
packet assembled as `{rising beat, falling beat}`. The frozen
`docs/PACKET.md` stores the rising beat in `packet[15:0]`.
`scripts/run_chisel_eth_replay.py` exchanges the two 16-bit halves and
leaves every bit inside a beat, and the cycle, unchanged.
`rpc.Replay` pokes `rpc.RpcTimingChecker` through ChiselTest and prints
`ACCEPT`, `VIOLATION`, or `INTERPRETATION`. Verilog for the same module
is `independent/cleanroom/generated/RpcTimingChecker.v`.

`refreshSelect` 0 reports `INTERPRETATION` when the agent's two
completion readings disagree, and `VIOLATION` when a command is early
under both. Select 1 uses 4096 row operations per selected bank.
Select 2 uses 5000 operations per bank, from the datasheet sentence
that four banks take 64 ms in low-power refresh. Both readings start
after the Table 11-3 maximum tRFQSd (3 x tREFI) and add tRFQSL. There
is still no tRFC in the datasheet. The agent did not collapse that gap
to one number.

## C. Which ETH commands were checked?

All replays use tCK = 5 ns. The MRS packet in these traces programs
CL = 8 and one-shot refresh. Rocket and BOOM were rerun from the
existing simulators on 2026-10-30. Both pin streams match the saved
logs command for command, and both hit `TestDriver.v:158`, which is
`$finish` after `io_success`. The workload
`workloads/rpc_banks.c` returns 0 only after 64 compared words on each
of the four banks.

| Trace | Commands | Banks activated | Chisel select 0 | Chisel select 1 | Chisel select 2 | Older Python `row_step` | SV observer |
|---|---:|---|---|---|---|---|---|
| Standalone ETH pin | 21 | 0 | 0 violations | 0 | 0 | 0 | not in this log |
| Rocket `rpc_banks` | 394 | 0, 1, 2, 3 | 0 | 0 | 0 | 0 | 0 |
| BOOM `rpc_banks` | 409 | 0, 1, 2, 3 | 0 | 0 | 0 | 0 | 0 |
| Directed stress | 99 | 0, 1, 2, 3 | 0 | 0 | 0 | 0 | 0 |
| Directed row-step REF | 57 | 0, 1, 2, 3 | 8 violations, 2 interpretations | 8 violations | 6 violations | 0 | 0 |
| `N_REF=2` | 45 | 0, 1, 2, 3 | 1 `REFRESH_BUSY` | 1 | 1 | 1 `tREFI` | 1 `tREFI` |
| `N_REF=20` | 45 | 0, 1, 2, 3 | 1 `REFRESH_BUSY` | 1 | 1 | 1 `tREFI` | 1 `tREFI` |

The committed summary is
`docs/evidence/chisel_eth_replay_2026-10-30.json`. The local transcript,
which `results/` does not commit, is
`results/differential/chisel-replay/sbt-all.out`.

Rocket, BOOM, the short standalone bench, and the stress bench issue
no REF. On those streams the new checker and the older Python checker
agree: no violations. Every data access is still closed-page ACT, one
column command, PRE. At 5 ns the checker's first legal column slot is
ACT+8. ETH uses ACT+16. Both are legal. They are different schedules.

## D. Can the checker detect illegal behavior?

Yes. Three categories stay separate.

**Observed controller configuration.** With `N_REF=2` the next ACT is
at cycle 42571. The checker reports `REFRESH_BUSY` under every reading.
The earliest cycle is 124536 for the 4096-row reading and 142616 for
the 5000-operation reading. The command is not moved. With `N_REF=20`
the ACT is at 42587, still one violation under every reading. The
older one-tREFI reading accepted 42587 (earliest 42575 was the short
wait only). The new checker does not treat one tREFI as the whole
one-shot busy time, so the intermediate wait is a definite violation
rather than an interpretation split.

The directed test that programs 81,920, 163,840, and 327,680 cycles
still completes its AXI readbacks. The frozen checker nevertheless
rejects the ACT that follows each of those refreshes:

| Banks | REF cycle | ACT offered | Gap | 4096-row earliest | Cycles early |
|---|---:|---:|---:|---:|---:|
| 1 | 42627 | 124563 | 81936 | 124608 | 45 |
| 2 | 124635 | 288491 | 163856 | 288536 | 45 |
| 4 | 288563 | 616259 | 327696 | 616304 | 45 |

The formula in the agent's traceability note is
`3 x tREFI + banks x 4096 x tREFI + tRFQSL`. At 5 ns that is
`60 + banks x 81920 + 1`. The controller waits `banks x 81920` and then
its usual 16-cycle command spacing, which is 45 cycles short of that
sum. The RD and PRE that follow each rejected ACT are
`RW_BANK_IDLE` and `PRE_BANK_PRECHARGED`. They are consequences of
leaving the bank closed, not additional controller schedules. Under
select 0, a later REF that is legal for 4096 rows and early for 5000
operations is `INTERPRETATION`, not a violation.

This is not a patched controller bug. The refresh FSM still waits for
the programmed `n_ref_*` value. That value matches the older row-step
estimate and omits the maximum tRFQSd and tRFQSL that this checker
stacks in front of the pass. No device waveform selects between those
formulas.

**Injected one-cycle faults.** On the Rocket stream the first RD is at
41563, which is ACT+16, and the checker accepts the whole trace. Moving
only that command to 41562 produces one line:
`VIOLATION TPPD_ACTIVE offered=41562 earliest=41563`. The other 393
commands stay accepted. Moving it to ACT+8 (41555) is accepted. Moving
it to ACT+7 produces `TPPD_ACTIVE` with earliest 41555. The boundary
that fails is one cycle before the boundary that passes. The committed lines are
`docs/evidence/chisel_eth_mutants_2026-10-30.txt`. The local sbt
transcript is `results/differential/chisel-replay/sbt-mutants.out`.

**The checker's own negative tests.** `results/selftest.txt` shows an
early RD reported as `TRCD` with earliest at the next legal slot, an
early PRE reported as `TBESL_WRITE`, and a post-refresh ACT reported
as `INTERPRETATION` under select 0 and as `VIOLATION` under select 2.
The agent's suite, 63 tests, covers the same boundaries. That suite is
not a substitute for the ETH replay above.

## E. Do Rocket and BOOM pass functional and timing checks?

Yes, for this workload.

Functional: both reruns finish at `TestDriver.v:158`. The failure path
in that file is `$fatal` when `failure` is set. `workloads/rpc_banks.c`
returns nonzero if any of the 64 words on a bank mismatches. The pin
memory, not the timing checker, supplied the bytes.

Timing: the same 394 and 409 pin commands, at their original cycles,
are accepted by `RpcTimingChecker` for refresh selects 0, 1, and 2.
Neither workload issues REF, so this does not speak to refresh.

The stress bench adds same-bank row changes, four reads posted before
any R beat (`accepted_before_r=4`, one handshake each), write-response
backpressure, and a 4-byte WSTRB. The readback is
`11223344aabbccdd`: the low four bytes changed and the upper four
remained. The pin write mask for that beat is `fffffff0`. All 99
commands are accepted by the checker, and the SV observer added no
violations. The command FSM still emits ACT, one column command, and
PRE. A second column to an open row was not observed and is not claimed.

## F. Discrepancies with the earlier models

These were left in place. The frozen checker was not edited to match
the older code or to make ETH pass.

| Topic | Frozen checker | Earlier Python / `IndRpcDramModel` / SV observer |
|---|---|---|
| One-shot duration | Not one tREFI. A pass is 4096 or 5000 operations per selected bank, after max tRFQSd, plus tRFQSL | `one_trefi` is one tREFI. `row_step` is 4096 x tREFI x banks, measured from the REF cycle. The SV observer uses `row_step` |
| `N_REF=20` (ACT at REF+32) | Violation under both pass lengths | Legal for `one_trefi`, illegal for `row_step` (earliest REF+81920 at 5 ns) |
| Programmed 81,920 / 163,840 / 327,680 waits | ACT is 45 cycles early under the 4096-row reading | Accepted by `row_step` and by the SV observer |
| Active-state grid | 8 CK. At 5 ns, tRCD is 3 and the first column slot is ACT+8 | Same grid. ETH issues ACT+16. `IndRpcDramModel` at 5 ns used ACT+8. Both slots are legal here |
| Next packet after a burst | RL or WL plus 8 CK per WORD, plus tBESL (9 read, 11 write), plus the 2 CK STB lead | End of the data burst, tWR, and the grid. No separate tBESL+2 term. The ETH gaps of about 48 CK clear both |
| nWR | Decoded from the MRS packet. No timing rule uses it. Parallel PRE uses tWR | nWR must be at least tWR in cycles |
| Idle PRE | Illegal except the post-reset precharge-all | A later idle PRE was an error in the Python checker as well; reset precharge-all is legal in both |
| Packet integer | Rising beat in `[15:0]` | Pin log stores the rising beat in `[31:16]`. The adapter swaps halves. Field decode then matches ACT, RD, MRS CL=8, and one-shot REF |
| Address map | Bank, row, and column come from the packet | FASED also has an ETH-like host address map. The datasheet does not define one |

The 45-cycle refresh gap is the difference between "wait out the row
walk" and "wait out maximum BUSY entry, the row walk, and tRFQSL".
Section 5 and Table 11-3 support tREFI, tRFQSd, and tRFQSL as separate
numbers and do not say that tRFQSd is already inside the row walk.
They also do not say that the walk is 4096 or 5000 steps. Both the
older row-step estimate and this checker's longer sum are inferences.

## G. What remains unresolved

- The datasheet still has no tRFC. The 4096-row and 5000-operation
  readings are both inferences. tRFQSd is a maximum, so a device can
  finish BUSY entry sooner than this checker allows.
- Loop-refresh exit is a CS# pulse, not a packet. The checker assumes
  the earliest legal pulse. These ETH traces use one-shot refresh.
- The production command FSM does not emit a second column to an open
  row. That case is tested in the checker and not claimed for ETH.
- Serial streaming, power-down, training, and analog setup and hold are
  outside the checker. Power-down entry is reported as `INTERPRETATION`
  and does not change bank state.
- Electrical timing, DQS BUSY waveforms, and retention were not
  measured. No U250, JTAG, or physical DRAM run was performed.
- The AXI fuzzer `error` signal is still tied low in the older FASED
  runs. Those runs are not data-integrity evidence. The data evidence
  in this report is the workload compare and the directed AXI readbacks.

## Validation matrix

| Experiment | Result | Evidence |
|---|---|---|
| Genuine isolation of model derivation | PASS, with the `stat` and logged-network limits in section A | `independent/cleanroom/PROVENANCE.md`; session `bfa1afa5-1b33-45d9-ad77-b8c613a81ca4` |
| Independent Chisel compilation | PASS | `results/sbt-test.txt`; `generated/RpcTimingChecker.v` |
| Independent timing-model unit tests | PASS | 63 tests, 0 failures |
| New Chisel command-input checking interface | PASS | `rpc.Replay` pokes `RpcTimingChecker`; early commands stay at the offered cycle |
| Standalone ETH commands through Chisel checker | PASS | 21 commands, 0 violations at 5 ns, selects 0, 1, and 2 |
| Rocket ETH commands through Chisel checker | PASS | 394 commands, 0 violations; rerun matches the saved pin log |
| BOOM ETH commands through Chisel checker | PASS | 409 commands, 0 violations; rerun matches the saved pin log |
| Legal REF configuration | FAIL under this checker | Three post-refresh ACTs are each 45 cycles early; older `row_step` and the SV observer accept them |
| Illegal REF configuration | PASS (detected) | `N_REF=2` and `N_REF=20` each produce one `REFRESH_BUSY` under every reading |
| Other negative timing tests | PASS | Rocket RD at ACT+16 passes; ACT+15 and ACT+7 fail with earliest on the next legal cycle. Agent self-test covers tRCD, tBESL, and refresh |
| Python versus Chisel comparison | PASS as a comparison, not as agreement | No-REF traces agree. Refresh earliest cycles differ by the tRFQSd plus tRFQSL term, and `N_REF=20` changes category |
| Functional readback through ETH | PASS | Rocket and BOOM `TestDriver.v:158`; stress readback `11223344aabbccdd`; directed bank and burst compares in the saved logs |
| Physical RPC DRAM | NOT RUN | No hardware access |

## What changed relative to `53511a361`

That commit documented the SV instantiation contract after the
same-rule Python and SV comparison. This work adds the isolated
checker, the half-swap replay of the real pin packets, the Rocket and
BOOM reruns, the `+stress` directed bench, and this report. ETH RTL
was not modified. The programmed refresh registers were not retuned to
satisfy the new checker.

Sagar's request is met for the experiment: a specification model built
in a separate session is what scores the controller's commands. It is
not met as a claim that every ETH configuration matches the device.
The no-refresh workloads pass both the functional compare and this
checker. The row-step refresh program that the older tools accepted is
early under the new completion formula, and the datasheet still does
not pick a single completion time. Physical BUSY measurements are
still required for that choice.
