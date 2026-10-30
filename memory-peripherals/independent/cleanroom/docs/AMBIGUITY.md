# Behavior the datasheet does not fully specify

Each item gives what the EM6GA16L Rev. 1.4 datasheet says, what is
missing or conflicting, and what the checker does. Item 1, the refresh
pass length, is the only missing numeric duration. It is the one kept
open through `refreshSelect` and `INTERPRETATION`. Items 2 to 5 cover
the rest of the refresh bound. The remaining items are gaps or conflicts
in wording, and each has one documented resolution.

## Refresh

### 1. Refresh pass length (no numeric duration)

Section 5 says a REF burst-refreshes the selected banks, with one
refresh operation every tREFI (100 ns FST, 3.2 us LP; Table 7-5,
Table 11-3). It never states how many operations a pass contains or
how long a REF takes. Two readings follow from the text:

- **Reading 1 (`refreshSelect` 1, rows-x-tREFI):** one operation per row.
  Table 1-2 gives 4096 rows (RA[0:11]), so a pass takes
  banks x 4096 x tREFI.
- **Reading 2 (`refreshSelect` 2, 64ms-statement):** section 5 says
  "under LP RF condition to refresh four full banks will take 64ms". With
  tREFI = 3.2 us that is 64 ms / (4 x 3.2 us) = 5000 operations per bank,
  so a pass takes banks x 5000 x tREFI. The same count is used for FST.

The readings disagree (4096 vs 5000) and the datasheet gives no other
duration, so the checker does not choose between them. Under
`refreshSelect` 0, a command that is legal under reading 1 but not under
reading 2 is reported as `INTERPRETATION constraint=REFRESH_BUSY`. Its
`detail` lists the earliest cycle under each reading. A command early
under both readings is a `VIOLATION`. Reading 2 is never shorter than
reading 1, so the checker reports the reading-1 earliest cycle for it.
docs/TRACEABILITY.md section 4 has the formulas and cycle tables.

### 2. tRFQSd has only a maximum

Table 11-3 gives "Latency from Refresh command to DQS/DQS# High (BUSY)
state" as max 3 x tREFI, with no minimum. A controller can watch DQS, but
the checker sees only the packet stream. Both readings therefore start
the pass at REF + 3 x tREFI, the latest the datasheet allows, so the
bound holds for any compliant device. A command that a controller
issues after watching DQS go low early would be reported as early by
this checker.

### 3. Loop refresh exit pulse

In loop mode (MRS CSRFX = 1, section 5.2, Figure 5-4, Figure 12-7) the
device refreshes until a CS# low pulse. The pulse is not a packet, so the
checker cannot see it. Section 5.2 allows it "only after tRFQSd". The
checker assumes the pulse comes at that first allowed point, REF + 3 x
tREFI. It then adds one full pass ("the DRAM will complete refreshing
all specified banks before exiting"), tRFQSL, the pulse width tCSLR
(2 ns min) and tPXCSL (10 ns). A later pulse moves the true completion
later by the same amount, which the checker cannot know.

### 4. What an INTERPRETATION does to state

docs/INTERFACE.md requires a command whose legality depends on the
unknown completion time to be reported as an interpretation, but does not
say whether state changes. The checker updates state as if refresh had
completed, for example opening the bank of an interpreted ACT. Later
commands are then checked against the device state that the reading
which made the command legal would produce. `accepted` stays 0 because
legality is not established, and Replay's `detail` ends with
`state-updated-as-if-refresh-complete`. Not updating state would turn
every later command to that bank into a state violation under every
reading, which would hide real timing errors. A wrapper that needs a
definite answer for every command runs with `refreshSelect` 1 or 2.

### 5. Clock stopped during refresh

Figure 12-7 says the clock "Can stop Toggling" during refresh (with
tCKSPE / tCKSPX). The checker counts cycles of a clock running at
`tckPs`, so a stopped clock is not modeled.

## Bank state

### 6. PRE to a bank that is already precharged

Table 8-3 marks PRE -> PRE (same bank) and REF -> PRE as Illegal with
note 11 ("Target bank should be in precharged state"). Table 8-4 marks
REF -> PRE Illegal (11), but PRE -> PRE (different bank) Legal. The
pattern is that PRE to a bank that is already precharged is illegal,
and the checker applies that to every bank selected by the mask
(`PRE_BANK_PRECHARGED`). A consequence is that PRE-all with any bank
already precharged is rejected. The one exception is the PRE-all of the
section 4 / Figure 2-3 reset sequence, where bank state is unknown after
RESET. Table 8-3 also marks MRS -> PRE (same bank) Legal. The checker
reads that cell as "legal when the bank is open". MRS does not change
bank state, so the PRE rule above still decides.

### 7. PRE or REF with no bank selected

Table 7-1 does not say what BK3..BK0 = 0000 does for PRE or REF. The
command would do nothing, and for REF it would leave unclear whether the
device goes BUSY. The checker rejects it as `PKT_NO_BANK`.

### 8. When Idle state begins after a precharge

Section 2.9 says Idle is entered on "Completing a Pre Charge All Bank
access" or "Completion of a Bank Pre Charge command when no other Bank is
activated". The checker takes completion to be PRE + tRP. Until then the
8-cycle tPPD grid of section 2.8 still applies. A command offered off the
grid before PRE + tRP is a `TPPD_ACTIVE` violation, and `earliest` is
the earlier of the next grid slot and PRE + tRP (when no bank is open).

### 9. tRP before MRS, ZQ and UTR

Figures 2-3 and 4-1 show PRE-all, then tRP, then MRS. Section 2.14 asks
for "all banks precharged and tRP met" before UTR, and section 3.11 asks
for "idle state with all banks precharged" before ZQ. The checker
requires every outstanding PRE + tRP before MRS, ZQ and UTR. Tables
8-3 / 8-4 mark PRE -> MRS "Legal" without saying when; the checker
reads that as "after tRP". Figure 12-12 notes 5 to 7 ("previous state
of MRS / UTR / ZQ calibration should be precharged state") support this.

### 10. MRS while a bank is open

Table 8-3 marks MRS -> READ / WRITE (same bank) Legal with note 8, "The
previous state of MRS should be active state", so MRS may be issued with
a bank open. Figure 12-12 note 5 says the previous state of MRS should
be precharged, but only in the context of the command after a Burst Stop
+ PRE. The checker allows MRS with banks open and still applies tMOD
before the next non-MRS command. ZQ and UTR, by contrast, require all
banks precharged (sections 3.11, 2.14).

### 11. REF after a write or a precharge

REF precharges all banks internally (sections 5.1, 5.2). The datasheet
does not give tWR or tRP before REF. The checker applies tRC from each
ACT (Table 11-3 "ACT to ACT or REF") and the tBESL bus window. It does
not apply tRP before REF. tWR before REF would never bind, because it
always ends before tBESL(write) + 2.

## Data timing

### 12. Where RL and WL are counted from

Section 3.8 says the latency "is measured from the end of the Request
Packet". Figures 2-14, 12-2, 12-6 and 2-13 draw RL / WL = AL + CL from
the clock edge that carries the packet. The checker follows the
figures: the first data beat is at `cycle + RL`. Under the section 3.8
wording every burst window, and so every `TBESL_*` bound, would be one
cycle later.

### 13. What "End of Burst" means for tBESL

Table 11-3 defines tBESL as "End of Burst to STB Low" in tCK. Figures
12-2 and 12-11 draw read data at RL + tDQSCK, but measure tBESL from the
end of the 8-cycle clock windows. The checker uses the clock-domain
burst end: cycle + RL + 8 x (BC + 1). It does not add tDQSCK
(2.5 to 7 ns), because that is an analog output delay, not a clock
count. Section 2.2 says STB goes low two clocks before a packet, so the
next packet is legal at burst end + tBESL + 2.

### 14. Reads with Zout open

Section 4 step 4 says Zout defaults to open "so it must be set as a
non-zero value, otherwise there will be no output from DRAM". The
checker treats an RD while Zout = 0000 as a usage error
(`READ_ZOUT_OPEN`) instead of a silent read. WR is allowed.

### 15. Write masks for a one-WORD burst

Table 7-1 gives WL-2 as the "1st DM" (first WORD) and WL-1 as the
"last DM" (last WORD). For BC = 0 the first and last WORD are the same
WORD. `ArrayModel` masks a byte if either mask bit is set. The checker
does not see mask beats.

### 16. Mode-register fields with no timing effect

nWR (Table 7-2) appears only in serial-packet figures: the internal
precharge after a serial Burst Stop + PRE (Figure 12-12) and serial REF
during a write burst (Figures 5-3, 5-6). A parallel PRE after a write
uses tWR (Figure 12-3). ODT, STBODT and ODTPD are analog termination
settings. The checker decodes and stores all four, but no modeled rule
depends on them.

## Initialization and ZQ

### 17. Start of the 200 us clock-stable period

Section 4 step 2 needs clocks stable for 200 us before PU RESET. The
datasheet has no "power-up cycle" marker in the packet stream. The
checker takes cycle 0 as the first stable clock. The first RESET must be
at cycle >= ceil(200 us / tCK).

### 18. The two serial resets of PU RESET

Section 4 step 3 and Figure 4-2 say PU Reset Entry is one parallel RESET
plus two serial RESETs on STB. Serial packets are not modeled, so the
checker assumes they follow the parallel RESET and measures tRESET from
the parallel RESET.

### 19. ZQINIT after a later RESET

Section 4 requires ZQ calibration at power-up. Section 2.10 and Figure
2-3 (reset outside power-up) show only PRE-all, tRP, MRS, tMOD, valid
command. The checker requires ZQINIT once after power-up, not after
every RESET.

### 20. ZQRESET quiet time

Section 3.11 says "There is no required quiet time after the ZQ RESET
command". Table 11-3 still lists tZQRESET = 50 ns min, and Figure 12-13
draws tZQRESET from ZQ RESET to the next valid command. The checker
enforces the Table 11-3 number (`TZQRESET`) and reads the section 3.11
sentence as being about data-bus quiet time.

## Configuration

### 21. Speed columns and clock periods

Table 11-3 has a single speed column (Speed-1600) with five tCK(avg)
rows (4, 2.5, 1.667, 1.5, 1.25 ns). Each row gives a minimum and no
maximum. The checker accepts any `tckPs` from 1250 to 65535 (the input
width) and allows a CL when tCK >= that CL's tCK(avg) minimum. The
1.667 ns entry is taken as 1667 ps, exactly as printed.

### 22. Cycle arithmetic width

Cycles are 64-bit. A bound that would pass 2^64 - 1 wraps. Traces are
expected to stay far below that.

### 23. `refreshSelect` value 3

The input is 2 bits wide. Value 3 is not a reading. The module treats it
like 0, and Replay rejects it as a usage error.

### 24. Data retention

Table 11-3 gives data retention of 64 ms (32 ms above 85 C). This is a
deadline for the controller, not a minimum between commands, and it
depends on temperature, which the checker does not know. The checker
does not enforce it.
