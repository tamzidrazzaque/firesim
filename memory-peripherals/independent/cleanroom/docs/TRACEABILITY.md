# Traceability

Authority: Etron EM6GA16L 256Mb RPC DRAM datasheet, Rev. 1.4, Oct. 2024
(`spec/EM6GA16L.pdf`). Section, table and figure numbers below refer to
that document. "Packet" means a parallel request packet (docs/PACKET.md).
All cycle numbers are device CLK cycles.

## 1. Where things live

| Item | File |
|---|---|
| Datasheet numbers (`RpcTimingParams`), speed rows, CL/nWR codes, refresh modes and readings | `src/main/scala/rpc/Spec.scala` |
| Decision logic (Chisel) | `src/main/scala/rpc/RpcTimingChecker.scala` |
| Replay program | `src/main/scala/rpc/Replay.scala` |
| Packet encoders (stimulus only) | `src/main/scala/rpc/Packet.scala` |
| Byte array for accepted RD/WR (stimulus side) | `src/main/scala/rpc/ArrayModel.scala` |
| Verilog | `generated/RpcTimingChecker.v` (`sbt "runMain rpc.EmitVerilog"`) |

The module takes the datasheet numbers as a Scala elaboration parameter
(`new RpcTimingChecker(p: RpcTimingParams)`). The tCK and refresh reading
are run-time inputs (`tckPs`, `refreshSelect`). Picosecond values become
cycles in hardware with `ceil(ps / tckPs)`, computed as
`(ps + tckPs - 1) / tckPs`. Values given in tCK stay in cycles.

## 2. Parameters

| Field | Value | Unit | Source |
|---|---|---|---|
| `tRCDPs` | 13 750 | ps | Table 11-3 tRCD min 13.75 ns |
| `tRPPs` | 13 750 | ps | Table 11-3 tRP min 13.75 ns |
| `tRCPs` | 48 750 | ps | Table 11-3 tRC min 48.75 ns ("ACT to ACT or REF") |
| `tRASPs` | 35 000 | ps | Table 11-3 tRAS min 35 ns |
| `tRRDPs` | 7 500 | ps | Table 11-3 tRRD min 7.5 ns |
| `tWRPs` | 15 000 | ps | Table 11-3 tWR min 15 ns |
| `tRESETPs` | 5 000 000 | ps | Table 11-3 tRESET min 5 us; section 2.10; section 4 step 3 |
| `tMRDCk` | 4 | tCK | Table 11-3 tMRD min 4 tCK |
| `tMODCk`, `tMODPs` | 12, 15 000 | tCK, ps | Table 11-3 tMOD min max(12 tCK, 15 ns) |
| `tPPDIdleCk` | 4 | tCK | Table 11-3 tPPD, Idle state, min 4 tCK |
| `tPPDActiveCk` | 8 | tCK | Table 11-3 tPPD, Activate state, "8 or 8's multiples"; section 2.8 |
| `tBESLReadCk` | 9 | tCK | Table 11-3 tBESL Read min 9 tCK |
| `tBESLWriteCk` | 11 | tCK | Table 11-3 tBESL Write min 11 tCK |
| `tZQINITPs` | 2 000 000 | ps | Table 11-3 tZQINIT min 2 us |
| `tZQCLPs` | 360 000 | ps | Table 11-3 tZQCL min 360 ns |
| `tZQCSPs` | 90 000 | ps | Table 11-3 tZQCS min 90 ns |
| `tZQRESETPs` | 50 000 | ps | Table 11-3 tZQRESET min 50 ns |
| `tREFIFstPs` | 100 000 | ps | Table 11-3 tREFI FST (REFOP0 = 0) 100 ns; Table 7-5 |
| `tREFILpPs` | 3 200 000 | ps | Table 11-3 tREFI LP (REFOP0 = 1) 3.2 us; Table 7-5 |
| `tRFQSdMaxInREFI` | 3 | x tREFI | Table 11-3 tRFQSd max 3 x tREFI |
| `tRFQSLPs` | 5 000 | ps | Table 11-3 tRFQSL min 5 ns |
| `tPXCSLPs` | 10 000 | ps | Table 11-3 tPXCSL min 10 ns; section 5.2 |
| `tCSLRPs` | 2 000 | ps | Table 11-3 tCSLR min 2 ns (loop refresh exit pulse) |
| `tckMinPs` | 1 250 | ps | Table 11-3 tCK(avg) min, CL = 11 row |
| `clMinTckPs` | CL3: 4000, CL8: 1667, CL10: 1500, CL11: 1250 | ps | Table 11-3 tCK(avg) rows (1.667 ns taken as 1667 ps) |
| `stbLeadCk` | 2 | tCK | Section 2.2: STB driven low two clock cycles before the packet; Figures 12-2, 12-3 |
| `additiveLatency` | 1 | tCK | Table 7-2: RL = AL + CL, AL = 1; WL = RL |
| `wordCk` | 8 | tCK | Section 2.4: one 32-byte WORD = 16 bus samples = 8 clocks; Figure 2-14 |
| `clockStablePs` | 200 000 000 | ps | Section 4 step 2: clocks stable for at least 200 us |
| `rowsPerBank` | 4096 | rows | Table 1-2: RA[0:11] |
| `lpFourBankPassPs` | 64 000 000 000 | ps | Section 5: "under LP RF condition to refresh four full banks will take 64ms" |

Encodings: CL codes and nWR codes from Table 7-2 (`RpcConfig.clCodes`,
`RpcConfig.nwrCodes`). Table 11-3 has one speed column (Speed-1600) with
five tCK(avg) rows. `RpcConfig.operatingPoints` lists all five:

| Row | tCK | CL |
|---|---|---|
| CL3-250MHz | 4000 ps | 3 |
| CL8-400MHz | 2500 ps | 8 |
| CL8-600MHz | 1667 ps | 8 |
| CL10-667MHz | 1500 ps | 10 |
| CL11-800MHz | 1250 ps | 11 |

The checker accepts any `tckPs` from 1250 to 65535, and any CL whose
minimum tCK is at or below the configured period.

## 3. Constraints

`constraintId` is stable. "Bound" constraints report the earliest cycle
at which the same command would be legal. "State" constraints cannot be
fixed by waiting, so they report `earliest = 0` (Replay prints `na`).
Times are measured between packet cycles, meaning the CLK rising edge
that carries the packet's first half.

### 3.1 Packet and configuration (state)

| Id | Name | Rule | Unit | Source |
|---|---|---|---|---|
| 1 | `PKT_UNDEFINED_OPCODE` | Opcode bits not in Table 7-1 | - | Table 7-1 |
| 2 | `MRS_CL_RESERVED` | MRS CL code not in {000, 001, 010, 110} | - | Table 7-2 |
| 3 | `MRS_CL_TCK` | MRS CL whose tCK(avg) min exceeds `tckPs` | ps | Table 11-3 tCK(avg) |
| 4 | `MRS_RESERVED_BIT` | MRS with F.DB15 = 1 (table shows fixed 0) | - | Table 7-2 |
| 5 | `REF_REFOP_RESERVED` | REF with REFOP1 = 1 | - | Table 7-5; section 5 ("REFOP1=1 is not defined") |
| 6 | `PKT_NO_BANK` | PRE or REF with BK3..BK0 = 0000 | - | Table 7-1; docs/AMBIGUITY.md |
| 7 | `CFG_TCK_RANGE` | `tckPs` < 1250 | ps | Table 11-3 tCK(avg) min |

### 3.2 Initialization and reset

| Id | Name | Kind | Rule | Unit | Source |
|---|---|---|---|---|---|
| 10 | `INIT_CLOCK_STABLE` | bound | First RESET at cycle >= ceil(200 us / tCK), counted from cycle 0 | ps -> tCK | Section 4 step 2; Figure 4-1 |
| 11 | `INIT_RESET_REQUIRED` | state | No command other than RESET before the first RESET | - | Section 4 step 3; Figures 4-1, 4-2 |
| 12 | `INIT_TRESET` | bound | Any command >= RESET + ceil(5 us / tCK) | ps -> tCK | Table 11-3 tRESET; section 2.10; Figure 2-3 |
| 13 | `INIT_PREA_REQUIRED` | state | After RESET the next command (other than RESET) is PRE with all four BK bits | - | Section 4 step 4; section 2.10; Figure 2-3 |
| 14 | `INIT_MRS_REQUIRED` | state | After that PRE, the next command (other than RESET) is MRS | - | Section 2.10 ("MRS should be applied"); section 4 step 4 |
| 15 | `INIT_ZQINIT_REQUIRED` | state | After the power-up MRS, only MRS, RESET or ZQ with ZQCOP = 00 until ZQINIT is accepted | - | Section 4 step 4; section 3.11 ("ZQINIT must be performed") |

### 3.3 Packet spacing, data bus, mode register, busy windows (bound)

| Id | Name | Rule | Unit | Source |
|---|---|---|---|---|
| 20 | `TPPD_IDLE` | In Idle state: offered >= previous accepted packet + 4 | tCK | Table 11-3 tPPD (Idle); section 2.9 |
| 21 | `TPPD_ACTIVE` | In Activate state: offered - previous accepted packet is a multiple of 8, and >= 8 | tCK | Table 11-3 tPPD (Activate); section 2.8 |
| 22 | `TBESL_READ` | After RD: offered >= RD + RL + 8 x (BC + 1) + 9 + 2 | tCK | Table 11-3 tBESL Read; section 2.2 (STB lead 2); section 2.4; Figures 12-2, 12-6, 2-14 |
| 23 | `TBESL_WRITE` | After WR: offered >= WR + WL + 8 x (BC + 1) + 11 + 2 | tCK | Table 11-3 tBESL Write; section 2.2; Figures 12-3, 12-6, 2-14 |
| 24 | `TMRD` | MRS after MRS: >= previous MRS + 4 | tCK | Table 11-3 tMRD |
| 25 | `TMOD` | Any command except RESET, and except MRS directly after MRS: >= last MRS or UTR + max(12 tCK, ceil(15 ns / tCK)) | tCK | Table 11-3 tMOD; Figures 2-3, 4-1 (MRS -> valid command), 2-13 (UTR -> RD, UTR -> valid) |
| 26 | `REFRESH_BUSY` | Any command >= REF + refresh completion (section 4 below) | ps -> tCK | Section 5, 5.1, 5.2; Table 11-3 tREFI, tRFQSd, tRFQSL, tCSLR, tPXCSL; Figures 5-1, 5-4; Table 8-3/8-4 note 1 |
| 27 | `TZQINIT` | Any command >= ZQ(ZQCOP 00) + ceil(2 us / tCK) | ps -> tCK | Table 11-3; section 3.11; Figure 12-13 |
| 28 | `TZQCL` | Any command >= ZQ(01) + ceil(360 ns / tCK) | ps -> tCK | same |
| 29 | `TZQCS` | Any command >= ZQ(10) + ceil(90 ns / tCK) | ps -> tCK | same |
| 30 | `TZQRESET` | Any command >= ZQ(11) + ceil(50 ns / tCK) | ps -> tCK | Table 11-3; Figure 12-13; docs/AMBIGUITY.md |

The device is in Activate state while any bank is open, or while a
precharge has not yet completed (PRE + tRP). Otherwise it is in Idle
state (sections 2.8 and 2.9; docs/AMBIGUITY.md). Each RD or WR replaces
the burst window, so only the most recent burst bounds the next packet.
RL = WL = 1 + CL, using CL from the most recent accepted MRS (Table
7-2). RESET restores CL to 8, the Table 7-2 default.

### 3.4 Bank state and bank timing

| Id | Name | Kind | Rule | Unit | Source |
|---|---|---|---|---|---|
| 40 | `ACT_BANK_ACTIVE` | state | ACT to a bank that is open | - | Table 8-3 (ACT/READ/WRITE -> ACT same bank: Illegal); section 2.15 ("Activate commands may only be issued to precharged Banks") |
| 41 | `TRP` | bound | ACT >= PRE(same bank) + tRP; MRS, ZQ and UTR >= every PRE + tRP | ps -> tCK | Table 11-3 tRP; Figures 2-3, 4-1 (PREA -> MRS); section 2.14 ("tRP met"); section 3.11 |
| 42 | `TRC` | bound | ACT >= ACT(same bank) + tRC; REF >= ACT(each bank) + tRC | ps -> tCK | Table 11-3 tRC ("ACT to ACT or REF") |
| 43 | `TRRD` | bound | ACT >= previous ACT (any bank) + tRRD | ps -> tCK | Table 11-3 tRRD; Figure 2-14 |
| 44 | `TRCD` | bound | RD/WR >= ACT(same bank) + tRCD (not RD in UTR mode) | ps -> tCK | Table 11-3 tRCD; Figure 2-14 |
| 45 | `TRAS` | bound | PRE >= ACT(each selected bank) + tRAS | ps -> tCK | Table 11-3 tRAS; Figure 2-14 |
| 46 | `TWR` | bound | PRE >= end of write data to that bank + tWR (end = WR + WL + 8 x (BC + 1)) | ps -> tCK | Table 11-3 tWR; Figure 12-3 |
| 47 | `RW_BANK_IDLE` | state | RD/WR to a bank that is not open | - | Table 8-3 (PRE/REF -> READ/WRITE same bank: Illegal); Table 8-4 (REF -> READ/WRITE: Illegal); section 2.15 |
| 48 | `PRE_BANK_PRECHARGED` | state | PRE selecting a bank known to be precharged | - | Table 8-3 PRE -> PRE and REF -> PRE (note 11); Table 8-4 REF -> PRE (note 11); docs/AMBIGUITY.md |
| 49 | `ZQ_REQUIRES_IDLE` | state | ZQ while any bank is open | - | Section 3.11 ("only ... in the idle state with all banks precharged") |
| 50 | `UTR_REQUIRES_IDLE` | state | UTR while any bank is open | - | Section 2.14 ("all banks must be in the idle state") |

With the datasheet values, tWR never ends after tBESL(write) + STB lead
at any allowed tCK, so `TWR` is checked but never reported on its own.
A test with a longer `tWRPs` shows it firing.

ACT opens the bank. PRE closes each selected bank. REF closes every bank
because the device "will precharge all banks first" (sections 5.1 and
5.2). RESET makes every bank unknown, and the following PRE-all makes
them known precharged. The checker does not apply tRP between REF's
internal precharge and the next command, because that time is inside the
refresh completion.

### 3.5 Utility register mode, data path, out of scope

| Id | Name | Kind | Rule | Unit | Source |
|---|---|---|---|---|---|
| 60 | `UTR_MODE_CMD` | state | While UTR mode is enabled, only RD, UTR and RESET | - | Section 2.14; Figure 2-13 notes |
| 70 | `READ_ZOUT_OPEN` | state | RD while MRS Zout = 0000 (open, the default) | - | Section 4 step 4 note; Table 7-2 Zout; docs/AMBIGUITY.md |
| 80 | `UNMODELED_POWER_DOWN` | interpretation | PD Entry or DPD Entry offered at a legal packet slot | - | Sections 2.11, 2.12; Figures 2-5, 2-6 (not modeled) |

### 3.6 Priority and earliest cycle

1. State constraints are checked in the order of the ids listed in the
   module's `stateChecks` (packet/config, then init, then UTR mode, then
   bank state). The first one that matches is reported, with
   `earliest = 0`.
2. Otherwise the checker takes every bound that applies and uses the
   largest, B. If the device is in Activate state, the earliest cycle is
   the first slot at or after max(B, offered) that lies on the 8-cycle
   grid from the previous accepted packet. If the device is in Idle
   state, it is max(B, offered, previous + 4). If every bank is closed
   but a precharge is still running, the checker also considers the
   cycle when the device becomes Idle and takes the earlier option.
3. If the offered cycle is below B, the constraint that set B is
   reported. If the offered cycle is past B but not a legal slot,
   `TPPD_ACTIVE` or `TPPD_IDLE` is reported.

## 4. Refresh completion and `refreshSelect`

The datasheet does not give a numeric refresh duration. Section 5 gives
the parts:

- REF -> BUSY (DQS high) within tRFQSd, max 3 x tREFI.
- One pass over the selected banks at tREFI per refresh operation.
- DQS low for tRFQSL, then Idle (one-shot, Figure 5-1). In loop mode
  (CSRFX = 1, Figure 5-4) there is also a CS# low exit pulse (tCSLR) and
  tPXCSL before the next command.

The number of refresh operations per bank in one pass is not stated. Two
readings are justified by the text (docs/AMBIGUITY.md, item 1):

| `refreshSelect` | Name | Operations per bank | Completion after REF |
|---|---|---|---|
| 0 | no-collapse | both computed | see below |
| 1 | rows-x-tREFI | 4096 (one per row, Table 1-2) | ceil((3 tREFI + banks x 4096 x tREFI + tRFQSL [+ tCSLR + tPXCSL]) / tCK) |
| 2 | 64ms-statement | 5000 (64 ms / (4 x 3.2 us), section 5) | ceil((3 tREFI + banks x 5000 x tREFI + tRFQSL [+ tCSLR + tPXCSL]) / tCK) |

`banks` is the number of BK bits set in the REF packet. tREFI comes from
REFOP0 in the REF packet (Table 7-5). The bracketed loop-mode term comes
from CSRFX in the last MRS. The module never treats refreshSelect 3 as
a reading. It behaves like 0, and Replay rejects 3 as a usage error.

Under `refreshSelect` 0, for a command offered while a refresh is
outstanding:

- Early under reading 1 (reading 2 is never shorter, so early under
  both): `VIOLATION`, with the reading-1 earliest cycle.
- Legal under reading 1, early under reading 2: `INTERPRETATION
  constraint=REFRESH_BUSY`. `earliest` is the reading-2 earliest cycle,
  and `detail` lists both. The checker then applies the command as if
  refresh had completed, so the rest of the trace is checked against the
  device state the command would create. The `detail` text says so.
  `accepted` stays 0.
- Legal under both: `ACCEPT`.

Under `refreshSelect` 1 or 2, the selected reading decides
`ACCEPT` or `VIOLATION`.

Cycle offsets from REF to completion (one-shot / loop):

| tCK (ps) | FST 1 bank rs1 | FST 1 bank rs2 | FST 4 banks rs1 | FST 4 banks rs2 | LP 4 banks rs1 | LP 4 banks rs2 |
|---|---|---|---|---|---|---|
| 1250 | 327924 / 327934 | 400244 / 400254 | 1310964 / 1310974 | 1600244 / 1600254 | 41950724 / 41950734 | 51207684 / 51207694 |
| 1500 | 273270 / 273278 | 333537 / 333545 | 1092470 / 1092478 | 1333537 / 1333545 | 34958937 / 34958945 | 42673070 / 42673078 |
| 1667 | 245894 / 245902 | 300123 / 300131 | 983027 / 983034 | 1199944 / 1199951 | 31456752 / 31456759 | 38398084 / 38398091 |
| 2500 | 163962 / 163967 | 200122 / 200127 | 655482 / 655487 | 800122 / 800127 | 20975362 / 20975367 | 25603842 / 25603847 |
| 4000 | 102477 / 102480 | 125077 / 125080 | 409677 / 409680 | 500077 / 500080 | 13109602 / 13109605 | 16002402 / 16002405 |

## 5. Derived cycle values

`ceil(time_ps / tck_ps)` for each tCK(avg) row (checked in
`RpcConfigSpec`):

| tCK (ps) | tRCD | tRP | tRC | tRAS | tRRD | tWR | tMRD | tMOD | tRESET | tZQINIT | tZQCL | tZQCS | tZQRESET | 200 us |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1250 | 11 | 11 | 39 | 28 | 6 | 12 | 4 | 12 | 4000 | 1600 | 288 | 72 | 40 | 160000 |
| 1500 | 10 | 10 | 33 | 24 | 5 | 10 | 4 | 12 | 3334 | 1334 | 240 | 60 | 34 | 133334 |
| 1667 | 9 | 9 | 30 | 21 | 5 | 9 | 4 | 12 | 3000 | 1200 | 216 | 54 | 30 | 119977 |
| 2500 | 6 | 6 | 20 | 14 | 3 | 6 | 4 | 12 | 2000 | 800 | 144 | 36 | 20 | 80000 |
| 4000 | 4 | 4 | 13 | 9 | 2 | 4 | 4 | 12 | 1250 | 500 | 90 | 23 | 13 | 50000 |

Bus-free offsets after a one-WORD burst, counted from the RD/WR packet
(RL + 8 + tBESL + 2):

| CL | RL | after RD | after WR |
|---|---|---|---|
| 3 | 4 | 23 | 25 |
| 8 | 9 | 28 | 30 |
| 10 | 11 | 30 | 32 |
| 11 | 12 | 31 | 33 |

In Activate state these round up to the next multiple of 8 from the
previous packet.

## 6. Diagram and table coverage

### Implemented (normal parallel-packet operation of one device)

| Item | How |
|---|---|
| Figure 1-1 state diagram, parallel part | Idle / Activate / Reset / Refresh / UTR states as above |
| Figure 2-3 parallel reset entry and exit | tRESET -> PRE-all -> tRP -> MRS -> tMOD |
| Figure 2-13 UTR timing | tMOD after UTREN = 1 and = 0, RD-only mode |
| Figure 2-14 cycle templates | tRRD, tRCD, tRAS, tRP, tRC, tPPD, RL / WL |
| Figure 4-1 power-up sequence, packet part | 200 us, RESET, tRESET, PRE-all, MRS, ZQINIT |
| Figure 5-1 one-shot refresh (parallel) | completion readings, banks closed |
| Figure 5-4 loop refresh (parallel) | as one-shot plus tCSLR and tPXCSL, exit pulse assumed at the earliest allowed point |
| Figures 12-2, 12-3, 12-4 back-to-back parallel commands | tBESL + STB lead, tPPD |
| Figure 12-6 latency origin | RL / WL from the packet's rising edge |
| Figure 12-7 full bank auto burst refresh | REF with 1 to 4 banks, tRFQSd, tCSLR, tRFQSL, tPXCSL (clock assumed running) |
| Figure 12-13 ZQ calibration timing | tZQINIT, tZQCL, tZQCS, tZQRESET |
| Tables 7-1 to 7-6 | decode, field extraction, reserved codes |
| Table 8-3, Table 8-4 (PAR to PAR) | bank-state rules 40, 47, 48, plus timing |
| Table 11-3 | every command-to-command timing listed in section 2 |

### Not implemented

| Item | Reason |
|---|---|
| Section 3.2 to 3.7 serial packets on STB: Tables 7-7, 7-8; Figures 2-2, 3-1, 3-2, 3-3, 3-4, 5-2, 5-3, 5-5, 5-6, 12-5, 12-8, 12-9, 12-10, 12-11, 12-12 (burst stop is a serial command); Tables 8-1, 8-2, 8-5 to 8-8; Table 3-1 bubble NOPs; tRTW, tWTR | Serial streaming is outside normal parallel-packet operation. The checker sees only parallel packets. |
| Clock stopped during refresh (Figure 12-7 "Can stop Toggling"); tCKSPE, tCKSPX | The checker counts cycles of a running clock at `tckPs`. |
| Figure 2-4 serial reset; the two serial resets of Figure 4-2 | serial packets; assumed to have been sent (docs/AMBIGUITY.md) |
| Figures 2-5, 2-6 power-down and deep power-down; tCKE, tDPD, tINIT, tCKSPE, tCKSPX | PD and DPD exit is signalled on CS# outside the packet stream. Entry is reported as `INTERPRETATION UNMODELED_POWER_DOWN` and does not change state. |
| Figures 2-7 to 2-11, Tables 2-3 to 2-6 ODT and Zout impedance | analog. ODT, STBODT and ODTPD are decoded but unused. Zout is used only for `READ_ZOUT_OPEN`. |
| Section 6 multi rank (Figures 6-1 to 6-7) | one device only |
| Figures 2-1, 12-1 request packet timing; tCSS, tCSH, tIS, tIH, tIS_STB, tIH_STB, tDS, tDH, tDQSS | sub-cycle analog setup and hold |
| tDQSCK, tDQSQ, tLZ, tHZ, tWPRE, tWPST, tRPRE, tRPST | sub-cycle data strobe timing. The bus window uses the clock-domain burst end (docs/AMBIGUITY.md). |
| Section 2.14 UTR data patterns (training) | the checker does not produce read data |
| Section 2.7 / Table 2-2 write data masks | data-path beats, applied by `ArrayModel` for accepted writes |
| Power ramp (section 4 step 1), data retention 64 ms / 32 ms, temperature-dependent refresh limits | not command timing; no deadline is enforced |
| Figure 1-2 block diagram, sections 1.5, 1.6, 9, 10, 11.1, 11.2, 13 | not timing |

## 7. Page policy

Parallel RD/WR packets carry no auto-precharge bit. Auto precharge only
exists in serial packets (section 3.2), which are not modeled. A
closed-page policy is therefore the caller sending PRE after the burst,
and the checker applies the same `TRAS`, `TWR` and `TBESL_*` rules to
it. An open-page policy simply leaves the bank open. The checker has no
page-policy setting of its own.

## 8. Tests

| Spec | Covers |
|---|---|
| `RpcConfigSpec` | speed rows, ceil conversion table above, CL-vs-tCK, refresh arithmetic |
| `PacketDecodeSpec` | every Table 7-1 opcode, field extraction, encoder bit positions |
| `InitSpec` | constraints 10 to 15, 2 to 4, 41, 25, 27, at every tCK(avg) row |
| `BankTimingSpec` | 20, 21, 40 to 48, early commands leave state unchanged |
| `DataTimingSpec` | 22 to 25, 46, 70, RL from MRS CL, burst length |
| `RefreshSpec` | 26 under refreshSelect 0, 1, 2; FST/LP, one-shot/loop, bank count, all tCK rows; 5, 6 |
| `UtrZqSpec` | 27 to 30, 49, 50, 60, 80, 1, 7, 20 |
| `ReplaySpec` | output format, `na`, refresh readings, second clock, exit codes 0/2/3 |
| `ArrayModelSpec` | byte masks; array changes only for commands the module accepted |

Most timing tests use `Bench.boundary`: the command is offered one cycle
before the bound and must be a `VIOLATION` with that constraint and the
bound as `earliest`. It is then offered at the bound and must be
accepted.
