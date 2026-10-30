# EM6GA16L speed-1600 timing model

Command-level model of one Etron 256Mb RPC DRAM (EM6GA16L family, Rev 1.4)
at the **1600** column of Table 11-3. There is no second reference implementation.
`tCK` is **1.25 ns** (800 MHz, CL=11, 1600 MT/s/pin).

Nanosecond minima become cycles with `ceil(time / tCK)`. The headline
command numbers are:

| Parameter | Cycles | Where it comes from |
| --- | --- | --- |
| tRCD | 11 | 13.75 ns, Table 11-3 |
| tRP | 11 | 13.75 ns, Table 11-3 |
| tRAS | 28 | 35 ns, Table 11-3 |
| tRC | 39 | 48.75 ns, Table 11-3 (equals tRAS+tRP) |
| tRRD | 6 | 7.5 ns, Table 11-3 |
| tWR | 12 | 15 ns, Table 11-3 |
| RL, WL | 12 | AL=1 fixed, CL=11, WL=RL (Table 7-2) |
| Burst | BL16 | 16 beats, 8 tCK, 32 bytes per WORD (Section 2.4) |
| Refresh busy | 80 | one-shot FST tREFI, 100 ns (Section 5, Table 11-3) |

`issue(command)` either accepts the command at the cycle the caller offered or
appends a violation `(constraint, offered cycle, earliest legal cycle)`. An
early command is not moved forward.

## Run the tests

From the parent of this directory:

```bash
cd /scratch/trazzaque/memory-peripherals/independent
/scratch/trazzaque/memory-peripherals/.venv/bin/python -m unittest discover -s rpc_fased/tests -v
```

`earliest_legal_cycle` is `None` when waiting cannot make that same command
legal (the bank is closed, the opcode is unknown, and similar state errors).

## Ambiguities

1. **Refresh duration.** Table 11-3 calls tREFI an average interval (100 ns FST,
   3.2 µs LP). Section 5 calls the same number the refresh period on entry and
   says one-shot mode accepts no command while BUSY. No tRFC is specified.
   One-shot REF is modeled as busy for exactly one tREFI (80 cycles FST, 2560
   LP), independent of how many banks are selected. tRFQSd (maximum 3×tREFI) is
   not added. tCKSPE, tCKSPX, tRFQSL, and tPXCSL are inside that window for
   one-shot mode. Loop mode (CSRFX=1) stays busy until `refresh_exit`, which is
   legal at REF+tCKSPE; the next command is legal at exit+tCKSPX. The datasheet
   also says the device finishes the current bank loop after the exit pulse;
   that extra time is not given a number and is not added.

2. **Active-state eight-clock grid.** Section 2.8 and Table 11-3 require
   intervals between parallel commands while a row is active to be 8 tCK or
   an integer multiple. The speed-1600 tRCD is 11 tCK, so the first legal CAS
   after ACT is at ACT+16; row-miss latency is 16+RL = 28. tRAS=28 similarly
   makes ACT+32 the first legal PRE slot. Once all banks are idle, the next
   command need only meet the idle tPPD minimum of 4 and other AC minima.
   With a legal PRE already issued, tRP=11 makes the earliest ACT-to-data
   portion 11+16+12 = 39 tCK. tRRD=6 is dominated by active tPPD=8.

3. **No tRTP.** Figure 12-11 starts PRE at the end of the read data burst.
   Same-bank PRE is legal at `max(ACT+tRAS, READ+RL+8×(BC+1))`. The constraint
   is named `read_to_precharge`. Table 8-3 marks same-bank READ/WRITE→PRE
   illegal; Figure 12-3 shows PRE after a write once tWR is met. The illegal
   entries are treated as “illegal until the burst and tWR/tRAS are satisfied.”

4. **tWTR / tRTW versus Table 3-1.** The AC table says 8 tCK minimum (80
   maximum) for CL=11. Table 3-1 lists 1 bubble for CL 5–12. One 8-cycle
   serial slot is 8 tCK, so the tables match. A direction change also has to
   clear the previous burst (`tCCD` = 8 tCK per WORD).

5. **nWR default is too small for 1600.** Table 7-2 defaults nWR to 8. tWR is
   15 ns = 12 tCK. MRS must program nWR ≥ 12 (12, 14, or 16). Recovery is
   `WRITE+WL+8×(BC+1)+max(tWR, nWR)`. If nWR is only the minimum, the
   violation is named tWR.

6. **Single-WORD masks.** Section 2.7 defines a first-WORD mask and a
   last-WORD mask. BC=0 is both. A byte is written only if both bits are 0.
   Bit 1 means “do not write.” Middle WORDs of a longer burst are not masked.

7. **tBESL is not stacked** on tWR or tRCD. Figure 12-3 shows tWR directly
   from the write data to PRE. tBESL (read 9, write 11) is only catalogued.

8. **Initialization.** Section 4 wants 200 µs of stable clocks, then reset,
   precharge-all, MRS, and ZQINIT. Cycle 0 is after that 200 µs. The checker
   requires reset → precharge-all → MRS → tMOD before ACT/READ/WRITE/REF.
   The precharge-all is allowed while banks are already idle, which Section 4
   draws and note 11 of the command tables would otherwise forbid. ZQ is
   enforced only when a ZQ command is issued. Zout=open (the MRS default)
   accepts writes and rejects reads, per Section 2.13.

9. **Power-up data and reset.** The datasheet does not define the array after
   power-up or reset. Bytes start at `0x00`. Reset clears the mode registers
   and the banks and keeps the bytes.

10. **Column address.** Note 2: CA[0:3] are not applied because BL=16. The
    column argument is CA[4:9], 0..63, one 32-byte WORD. Bursts wrap inside
    the 2KB page and do not cross rows.

11. **Command cycle.** The integer cycle is the request-packet CK edge, not
    the STB-low two clocks earlier (Section 3.3). Sub-cycle timings (tIS, tDS,
    tWPRE, tWPST, …) are catalogued and are not command gaps.

12. **tMRD versus tMOD.** The datasheet does not say which commands each one
    separates. tMRD (4) is MRS-to-MRS. tMOD (12) is MRS to any other command.
    That matches the usual meaning of “cycle time” versus “update delay.”

13. **tODT formulas.** Table 2-6 adds `(RL-2)` to a nanosecond quantity and
    writes “+ 3” next to tDQSCK. Those are evaluated as `(RL-2)×tCK + tLZ` and
    `tDQSCK + 3 ns`. They are not command constraints.

14. **Closed page.** Table 7-1 has no auto-precharge bit on READ/WRITE. The
    caller sets `auto_precharge=True` to ask for the precharge that BST+PRE
    would perform, at the earliest cycle an explicit PRE would be legal.
    `page_policy` does not precharge by itself.

15. **Other CL codes and speed bins** are in the tables. This model is locked
    to CL=11 and tCK=1.25 ns. A different CL is rejected.

16. **Serial streaming, toggle bubbles beyond the minimum, UTR, ODT switching,
    and power-down** are not separate commands. A parallel burst ends when its
    burst count completes. Pipelined ACT to another openable bank is just an
    ACT during a burst, subject to tRRD and tPPD.
