"""Timing parameters for the Etron EM6GA16L 256Mb RPC DRAM, speed-1600.

All numbers come from EM6GA16L Rev 1.4. Nanosecond, microsecond, millisecond,
and picosecond minima are converted to cycles with ceil(time / tCK). tCK is
the speed-1600 value, 1.25 ns (800 MHz, CL=11).

`source` is "specified" when the datasheet states the number and "inferred"
when the model derives it (a formula, a cycle conversion of a stated minimum
into a command spacing the table does not name, or a choice among encodings).
"""

from __future__ import annotations

from dataclasses import dataclass

TCK_PS = 1250  # 1.25 ns


def cycles_from_ps(picoseconds: int) -> int:
    """Ceil of picoseconds / tCK without binary-fraction rounding."""
    if picoseconds < 0:
        raise ValueError(picoseconds)
    return (picoseconds + TCK_PS - 1) // TCK_PS


def _ns(ns: float) -> int:
    return cycles_from_ps(round(ns * 1000))


@dataclass(frozen=True, slots=True)
class TimingParam:
    name: str
    value: float
    unit: str
    cycles: int | None
    section: str
    page: int
    source: str
    note: str = ""
    bound: str = "min"
    picoseconds: int | None = None

    def __post_init__(self) -> None:
        if self.source not in ("specified", "inferred"):
            raise ValueError(self.source)
        if self.picoseconds is not None and self.cycles != cycles_from_ps(self.picoseconds):
            raise ValueError(f"{self.name}: cycles {self.cycles} != ceil(ps)")


def _p(
    name: str,
    value: float,
    unit: str,
    cycles: int | None,
    section: str,
    page: int,
    source: str,
    note: str = "",
    bound: str = "min",
    picoseconds: int | None = None,
) -> TimingParam:
    return TimingParam(name, value, unit, cycles, section, page, source, note, bound, picoseconds)


class P:
    """Adopted speed-1600 command timings, in integer tCK cycles unless noted."""

    tCK_ps = TCK_PS
    tCK_ns = 1.25
    fCK_MHz = 800
    data_rate_mtps = 1600

    # Table 11-3, page 59. These divide 1.25 ns exactly.
    tRCD = cycles_from_ps(13_750)  # 11
    tRP = cycles_from_ps(13_750)  # 11
    tRC = cycles_from_ps(48_750)  # 39
    tRAS = cycles_from_ps(35_000)  # 28
    tWR = cycles_from_ps(15_000)  # 12
    tRRD = cycles_from_ps(7_500)  # 6
    tMRD = 4
    tMOD = max(12, cycles_from_ps(15_000))  # max(12 tCK, 15 ns) = 12
    tRESET = cycles_from_ps(5_000_000)  # 5 us
    tCSS = cycles_from_ps(10_000)
    tCSH = cycles_from_ps(5_000)
    tREFI_FST = cycles_from_ps(100_000)  # 100 ns
    tREFI_LP = cycles_from_ps(3_200_000)  # 3.2 us
    tPPD_ACT = 8
    tPPD_IDLE = 4
    tCKSPE = 10
    tCKSPX = 10
    tPXCSL = cycles_from_ps(10_000)
    tRFQSL = cycles_from_ps(5_000)
    tRFQSd_FST = 3 * cycles_from_ps(100_000)  # max, not a minimum
    tRTW = 8
    tWTR = 8
    tRTW_MAX = 80
    tWTR_MAX = 80
    tZQINIT = cycles_from_ps(2_000_000)  # 2 us
    tZQCL = cycles_from_ps(360_000)
    tZQCS = cycles_from_ps(90_000)
    tZQRESET = cycles_from_ps(50_000)
    tCKE = max(cycles_from_ps(7_500), 3)
    tBESL_RD = 9
    tBESL_WR = 11
    tDPD = cycles_from_ps(500_000_000)
    tINIT = cycles_from_ps(200_000_000)
    tCLK_STABLE = cycles_from_ps(200_000_000)
    tCSLR_MIN = cycles_from_ps(2_000)
    tCSLR_MAX = cycles_from_ps(5_000)

    # Table 7-2 and the speed-1600 column of Table 11-3.
    AL = 1
    CL = 11
    RL = AL + CL  # 12
    WL = RL  # Table 7-2: WL = RL
    BL_BEATS = 16
    word_clocks = 8  # one 32-byte WORD on a DDR x16 bus
    nWR_MIN = tWR  # smallest Table 7-2 code that meets tWR at this tCK

    # Inferred one-shot occupancy. See README.
    tREF_BUSY_FST = tREFI_FST
    tREF_BUSY_LP = tREFI_LP

    row_hit_cycles = RL
    act_to_cas = ((tRCD + tPPD_ACT - 1) // tPPD_ACT) * tPPD_ACT
    act_to_pre = ((tRAS + tPPD_ACT - 1) // tPPD_ACT) * tPPD_ACT
    row_miss_cycles = act_to_cas + RL
    row_conflict_cycles = tRP + act_to_cas + RL
    read_to_precharge_bc0 = RL + word_clocks


class Geometry:
    banks = 4
    rows = 4096  # RA[0:11]
    columns = 64  # CA[4:9]; CA[0:3] are not applied (BL16)
    word_bytes = 32
    page_bytes = 2048
    data_width = 16
    density_mbit = 256


GEOMETRY = Geometry()
ALLOWED_NWR = (4, 6, 7, 8, 10, 12, 14, 16)
ALLOWED_CL_CODES = (3, 8, 10, 11)


def burst_clocks(burst_count: int, word_clocks: int = P.word_clocks) -> int:
    """Clocks occupied by a parallel burst. BC=0 is one WORD."""
    return (burst_count + 1) * word_clocks


def _catalog() -> tuple[TimingParam, ...]:
    s = "specified"
    i = "inferred"
    ac = "Table 11-3"
    items = [
        _p("tCK", 1.25, "ns", 1, ac, 59, s, "Speed-1600, CL=11, 800 MHz, 1600 MT/s/pin. Adopted device clock.", picoseconds=1250),
        _p("tCK_CL3", 4.0, "ns", None, ac, 59, s, "250 MHz bin. Not used; the model is locked to speed-1600."),
        _p("tCK_CL8_400", 2.5, "ns", None, ac, 59, s, "400 MHz bin. Not used."),
        _p("tCK_CL8_600", 1.667, "ns", None, ac, 59, s, "600 MHz bin as printed (1.667 ns). Not used."),
        _p("tCK_CL10", 1.5, "ns", None, ac, 59, s, "667 MHz bin. Not used."),
        _p("tRCD", 13.75, "ns", P.tRCD, ac, 59, s, "ACT to internal read or write.", picoseconds=13_750),
        _p("tRP", 13.75, "ns", P.tRP, ac, 59, s, "PRE command period.", picoseconds=13_750),
        _p("tRC", 48.75, "ns", P.tRC, ac, 59, s, "ACT to ACT or REF. Equals tRAS+tRP in both ns and cycles.", picoseconds=48_750),
        _p("tRAS", 35.0, "ns", P.tRAS, ac, 59, s, "ACTIVE to PRECHARGE.", picoseconds=35_000),
        _p("tRESET", 5.0, "us", P.tRESET, f"{ac}; Section 4", 59, s, "Also Figure 4-1 / Section 2.10.", picoseconds=5_000_000),
        _p("tCSS", 10.0, "ns", P.tCSS, ac, 59, s, "CS# setup. Pin timing, not a command gap.", picoseconds=10_000),
        _p("tCSH", 5.0, "ns", P.tCSH, ac, 59, s, "CS# hold. Pin timing, not a command gap.", picoseconds=5_000),
        _p("tWR", 15.0, "ns", P.tWR, ac, 59, s, "Write recovery. Figure 12-3 places it after the write data.", picoseconds=15_000),
        _p("tMRD", 4, "tCK", P.tMRD, ac, 59, s, "Mode Register Set command cycle time. Enforced MRS-to-MRS."),
        _p("tRRD", 7.5, "ns", P.tRRD, ac, 59, s, "ACT to ACT, any bank. At this speed tPPD_ACT is stricter.", picoseconds=7_500),
        _p("tIS", 170, "ps", cycles_from_ps(170), ac, 59, s, "Sub-cycle CS# setup. Catalogued only.", picoseconds=170),
        _p("tIH", 120, "ps", cycles_from_ps(120), ac, 59, s, "Sub-cycle CS# hold. Catalogued only.", picoseconds=120),
        _p("tIS_STB", 10, "ps", cycles_from_ps(10), ac, 59, s, "Sub-cycle STB setup. Catalogued only.", picoseconds=10),
        _p("tIH_STB", 45, "ps", cycles_from_ps(45), ac, 59, s, "Sub-cycle STB hold. Catalogued only.", picoseconds=45),
        _p("tDS", 10, "ps", cycles_from_ps(10), ac, 59, s, "Sub-cycle data setup. Catalogued only.", picoseconds=10),
        _p("tDH", 45, "ps", cycles_from_ps(45), ac, 59, s, "Sub-cycle data hold. Catalogued only.", picoseconds=45),
        _p("tRET", 64, "ms", cycles_from_ps(64_000_000_000), ac, 59, s, "Data retention, -40 C to +85 C. Maximum.", "max", 64_000_000_000),
        _p("tRET_HOT", 32, "ms", cycles_from_ps(32_000_000_000), ac, 59, s, "Data retention, +85 C to +95 C. Maximum.", "max", 32_000_000_000),
        _p("tDQSCK_min", 2.5, "ns", cycles_from_ps(2_500), ac, 59, s, "DQS output access, minimum.", picoseconds=2_500),
        _p("tDQSCK_max", 7.0, "ns", cycles_from_ps(7_000), ac, 59, s, "DQS output access, maximum. 7/1.25 = 5.6, ceil 6.", "max", 7_000),
        _p("tDQSQ", 135, "ps", cycles_from_ps(135), ac, 59, s, "DQS to DB skew, maximum.", "max", 135),
        _p("tREFI_FST", 100, "ns", P.tREFI_FST, f"{ac}; Section 5", 59, s, "FST refresh, REFOP=00. Also called the refresh period on entry.", picoseconds=100_000),
        _p("tREFI_LP", 3.2, "us", P.tREFI_LP, f"{ac}; Section 5", 59, s, "LP refresh, REFOP=01.", picoseconds=3_200_000),
        _p("tPPD_ACT", 8, "tCK", P.tPPD_ACT, f"{ac}; Section 2.8", 59, s, "Active-state parallel-command intervals are 8 CK or integer multiples, not just a minimum of 8."),
        _p("tPPD_IDLE", 4, "tCK", P.tPPD_IDLE, f"{ac}; Section 2.9", 59, s, "Minimum parallel-command spacing when every bank is precharged."),
        _p("tWPRE", 0.9, "tCK", None, ac, 59, s, "Write preamble. Fractional tCK, not a command slot."),
        _p("tWPST_CL3", 0.5, "tCK", None, ac, 59, s, "Write postamble at CL=3. Not the speed-1600 value."),
        _p("tWPST", 4.5, "tCK", None, ac, 59, s, "Write postamble at CL=8 and CL=10 to 11."),
        _p("tMOD", 12, "tCK", P.tMOD, ac, 59, s, "max(12 tCK, 15 ns). 15 ns converts to 12 tCK, so the minimum is 12. Enforced from MRS to a non-MRS command."),
        _p("tBESL_RD", 9, "tCK", P.tBESL_RD, ac, 59, s, "End of burst to STB low, read. Catalogued; not added on top of tRCD or RL."),
        _p("tBESL_WR", 11, "tCK", P.tBESL_WR, ac, 59, s, "End of burst to STB low, write. Catalogued; not added on top of tWR."),
        _p("tDPD", 500, "us", P.tDPD, ac, 59, s, "Minimum deep power-down period. Not a modeled command.", picoseconds=500_000_000),
        _p("tRFQSL", 5, "ns", P.tRFQSL, ac, 59, s, "DQS low time after leaving BUSY. Inside the one-shot window; not added to it.", picoseconds=5_000),
        _p("tCKSPE", 10, "tCK", P.tCKSPE, ac, 59, s, "Valid clocks after refresh, PD, or DPD entry. Loop-refresh exit may not precede this."),
        _p("tCKSPX", 10, "tCK", P.tCKSPX, ac, 60, s, "Valid clocks before refresh, PD, or DPD exit. Enforced after loop refresh_exit."),
        _p("tRFQSd_FST", 300, "ns", P.tRFQSd_FST, ac, 60, s, "Maximum latency from REF to DQS high. 3 x tREFI. Not a minimum command delay.", "max", 300_000),
        _p("tPXCSL", 10, "ns", P.tPXCSL, ac, 60, s, "Latency from leaving refresh or PD to CS# low. Not added on top of the one-shot tREFI window.", picoseconds=10_000),
        _p("tCSLR_min", 2, "ns", P.tCSLR_MIN, ac, 60, s, "Loop-mode CS# low pulse, minimum. 2/1.25 = 1.6, ceil 2.", picoseconds=2_000),
        _p("tCSLR_max", 5, "ns", P.tCSLR_MAX, ac, 60, s, "Loop-mode CS# low pulse, maximum.", "max", 5_000),
        _p("tRTW", 8, "tCK", P.tRTW, ac, 60, s, "Read-burst to write-burst, CL=8 and CL=10 to 11. Minimum."),
        _p("tRTW_max", 80, "tCK", P.tRTW_MAX, ac, 60, s, "Maximum toggle bubble, note 9.1. Not enforced as a timeout.", "max"),
        _p("tWTR", 8, "tCK", P.tWTR, ac, 60, s, "Write-burst to read-burst, CL=8 and CL=10 to 11. Minimum."),
        _p("tWTR_max", 80, "tCK", P.tWTR_MAX, ac, 60, s, "Maximum toggle bubble. Not enforced as a timeout.", "max"),
        _p("tLZ_DQS", 2.2, "ns", cycles_from_ps(2_200), ac, 60, i, "tDQSCK(min) - 300 ps = 2.2 ns.", picoseconds=2_200),
        _p("tLZ_DB", 2.2, "ns", cycles_from_ps(2_200), ac, 60, i, "Same formula as tLZ(DQS).", picoseconds=2_200),
        _p("tHZ_DQS", 6.9, "ns", cycles_from_ps(6_900), ac, 60, i, "tDQSCK(max) - 100 ps = 6.9 ns. Maximum.", "max", 6_900),
        _p("tHZ_DB", 7.189, "ns", cycles_from_ps(7_189), ac, 60, i, "tDQSCK(max) + 1.4 * tDQSQ(max) = 7.189 ns. Maximum.", "max", 7_189),
        _p("tZQINIT", 2, "us", P.tZQINIT, ac, 60, s, "Initialization calibration. Enforced only if a ZQ init command is issued.", picoseconds=2_000_000),
        _p("tZQCL", 360, "ns", P.tZQCL, ac, 60, s, "Long calibration.", picoseconds=360_000),
        _p("tZQCS", 90, "ns", P.tZQCS, ac, 60, s, "Short calibration.", picoseconds=90_000),
        _p("tZQRESET", 50, "ns", P.tZQRESET, ac, 60, s, "ZQ reset.", picoseconds=50_000),
        _p("tRPRE", 0.9, "tCK", None, ac, 60, s, "Read preamble. Fractional tCK."),
        _p("tRPST", 0.3, "tCK", None, ac, 60, s, "Read postamble. Fractional tCK."),
        _p("tCKE", 6, "tCK", P.tCKE, ac, 60, s, "max(7.5 ns, 3 tCK) = max(6, 3) = 6. PD is not a modeled command."),
        _p("tDQSS_min", -0.25, "tCK", None, ac, 60, s, "DQS edge to CK edge, minimum.", "min"),
        _p("tDQSS_max", 0.25, "tCK", None, ac, 60, s, "DQS edge to CK edge, maximum.", "max"),
        _p("tINIT", 200, "us", P.tINIT, ac, 60, s, "DPD exit to a valid command. DPD is not modeled.", picoseconds=200_000_000),
        _p("tCLK_STABLE", 200, "us", P.tCLK_STABLE, "Section 4", 42, s, "Clocks stable before reset. Assumed already satisfied at cycle 0.", picoseconds=200_000_000),
        _p("tPWR_RAMP", 200, "ms", cycles_from_ps(200_000_000_000), "Section 4", 42, s, "Power ramp maximum, 300 mV to VDDmin.", "max", 200_000_000_000),
        _p("tODToff_min", 1.75, "ns", cycles_from_ps(1_750), "Table 2-6", 26, s, "Catalogued only.", picoseconds=1_750),
        _p("tODToff_max", 3.5, "ns", cycles_from_ps(3_500), "Table 2-6", 26, s, "Catalogued only.", "max", 3_500),
        _p("tODTon_min", 1.75, "ns", cycles_from_ps(1_750), "Table 2-6", 26, s, "Catalogued only.", picoseconds=1_750),
        _p("tODTon_max", 3.5, "ns", cycles_from_ps(3_500), "Table 2-6", 26, s, "Catalogued only.", "max", 3_500),
        _p("tODTd", 12, "ns", cycles_from_ps(12_000), "Table 2-6", 26, s, "Maximum Rtt disable from power-down entry.", "max", 12_000),
        _p("tODTRoff_min", 14.7, "ns", cycles_from_ps(14_700), "Table 2-6", 26, i, "Interpreted as (RL-2)*tCK + tLZ(DQS)min = 10*1.25 ns + 2.2 ns.", picoseconds=14_700),
        _p("tODTRoff_max", 19.5, "ns", cycles_from_ps(19_500), "Table 2-6", 26, i, "Interpreted as (RL-2)*tCK + tDQSCK(max).", "max", 19_500),
        _p("tODTRon_min", 5.5, "ns", cycles_from_ps(5_500), "Table 2-6", 26, i, "Interpreted as tDQSCK(min) + 3 ns.", picoseconds=5_500),
        _p("tODTRon_max", 10.0, "ns", cycles_from_ps(10_000), "Table 2-6", 26, i, "Interpreted as tDQSCK(max) + 3 ns.", "max", 10_000),
        _p("AL", 1, "tCK", P.AL, "Table 7-2; Figure 12-2 note 3", 51, s, "Additive latency is fixed at 1."),
        _p("CL", 11, "tCK", P.CL, "Table 11-3; Table 7-2", 59, s, "Speed-1600 column is CL=11. MRS encoding 010."),
        _p("RL", 12, "tCK", P.RL, "Table 7-2; Section 3.8", 51, i, "RL = AL + CL = 12. Command-to-first-read-data on an open row."),
        _p("WL", 12, "tCK", P.WL, "Table 7-2; Figure 2-2", 51, s, "WL = RL. Figure 2-2 draws WL=12, AL=1, CL=11."),
        _p("BL", 16, "beats", P.BL_BEATS, "Section 2.4; Table 11-2 note 1", 14, s, "Fixed BL16. One WORD is 16 DDR beats on x16, which is 8 tCK and 32 bytes."),
        _p("tWORD", 8, "tCK", P.word_clocks, "Section 2.4", 14, s, "A 32-byte WORD takes 8 bus clocks at any BC. BC=0 transfers one WORD."),
        _p("nWR_MIN", 12, "tCK", P.nWR_MIN, "Table 7-2; Table 11-3", 51, i, "Smallest nWR code (4,6,7,8,10,12,14,16) that meets tWR=15 ns. The MRS default of 8 does not."),
        _p("tREF_BUSY_FST", 80, "tCK", P.tREF_BUSY_FST, "Section 5; Table 11-3", 44, i, "One-shot FST busy window, taken to be one tREFI (100 ns). No tRFC is specified."),
        _p("tREF_BUSY_LP", 2560, "tCK", P.tREF_BUSY_LP, "Section 5; Table 11-3", 44, i, "One-shot LP busy window, taken to be one LP tREFI (3.2 us)."),
        _p("row_hit", 12, "tCK", P.row_hit_cycles, "Table 7-2; Table 11-3", 51, i, "Open-row READ/WRITE to first data = RL = WL = 12."),
        _p("row_miss", 28, "tCK", P.row_miss_cycles, "Section 2.8; Table 11-3; Table 7-2", 59, i, "Idle bank: ACT to first CAS is 16 CK after 11-CK tRCD rounds to the next 8-CK command slot; plus RL=12."),
        _p("row_conflict", 39, "tCK", P.row_conflict_cycles, "Section 2.8; Table 11-3; Table 7-2", 59, i, "From a legal PRE with tRAS already met: tRP=11, ACT-to-CAS=16, RL=12. PRE timing may add a separate grid delay."),
        _p("read_to_precharge_bc0", 20, "tCK", P.read_to_precharge_bc0, "Figure 12-11; Section 2.5", 66, i, "No tRTP is specified. For BC=0, PRE is legal at READ+RL+8, and not before tRAS. Datasheet has no symbol for this."),
        _p("tRTW_bubbles", 1, "bubbles", 8, "Table 3-1", 35, i, "Table 3-1 lists 1 bubble for CL 5-12. One 8-cycle serial slot equals the AC minimum of 8 tCK."),
        _p("BC_MAX", 63, "count", 64, "Section 3.10; Table 7-3", 40, s, "BC=0 is one WORD and BC=63 is 64 WORDs. The cycle column here is the WORD count, not a delay."),
    ]
    return tuple(items)


ALL_PARAMS: tuple[TimingParam, ...] = _catalog()
BY_NAME = {p.name: p for p in ALL_PARAMS}

assert len(BY_NAME) == len(ALL_PARAMS)
assert P.tRAS + P.tRP == P.tRC
assert cycles_from_ps(35_000 + 13_750) == P.tRC
assert P.RL == 12 and P.WL == 12
assert P.row_hit_cycles == 12
assert P.act_to_cas == 16
assert P.act_to_pre == 32
assert P.row_miss_cycles == 28
assert P.row_conflict_cycles == 39
assert P.tREF_BUSY_FST == 80
assert P.tREFI_LP == 2560
assert P.nWR_MIN == 12
assert P.tMOD == 12
assert P.tCKE == 6


ADOPTED = {
    "tCK_ns": P.tCK_ns,
    "fCK_MHz": P.fCK_MHz,
    "CL": P.CL,
    "AL": P.AL,
    "RL": P.RL,
    "WL": P.WL,
    "BL_beats": P.BL_BEATS,
    "word_clocks": P.word_clocks,
    "tRCD": P.tRCD,
    "tRP": P.tRP,
    "tRAS": P.tRAS,
    "tRC": P.tRC,
    "tRRD": P.tRRD,
    "tWR": P.tWR,
    "nWR": P.nWR_MIN,
    "refresh_duration": P.tREF_BUSY_FST,
}
