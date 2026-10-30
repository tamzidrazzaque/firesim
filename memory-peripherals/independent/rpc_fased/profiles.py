"""Clock profiles for the same EM6GA16L checks.

The speed-1600 numbers live on `params.P`. This module only converts those
nanosecond minima at another tCK. A tCK-counted minimum (tPPD, tMRD, tCKSPE)
stays in cycles. This file was added after the isolated speed-1600 model so
a 200 MHz controller trace can be checked without pretending the controller
runs at 1.25 ns.
"""

from __future__ import annotations

from dataclasses import dataclass

from .params import ALLOWED_NWR, P

# Table 11-3 tCK(avg) minimum for each CL code. A slower clock (larger tCK)
# is not given a maximum in that table.
CL_MIN_TCK_PS = {
    3: 4_000,
    8: 2_500,
    10: 1_500,
    11: 1_250,
}


def cycles(picoseconds: int, tck_ps: int) -> int:
    if picoseconds < 0 or tck_ps <= 0:
        raise ValueError((picoseconds, tck_ps))
    return (picoseconds + tck_ps - 1) // tck_ps


@dataclass(frozen=True)
class ClockProfile:
    tck_ps: int
    CL: int
    AL: int
    RL: int
    WL: int
    tRCD: int
    tRP: int
    tRAS: int
    tRC: int
    tRRD: int
    tWR: int
    tPPD_ACT: int
    tPPD_IDLE: int
    tMRD: int
    tMOD: int
    tRESET: int
    tREFI_FST: int
    tREFI_LP: int
    tREF_BUSY_FST: int
    tREF_BUSY_LP: int
    tRTW: int
    tWTR: int
    tCKSPE: int
    tCKSPX: int
    tZQINIT: int
    tZQCL: int
    tZQCS: int
    tZQRESET: int
    word_clocks: int
    nWR_MIN: int
    allowed_cl: tuple[int, ...]

    @property
    def name(self) -> str:
        return f"tCK={self.tck_ps}ps CL={self.CL}"


def profile_for(tck_ps: int, cl: int | None = None) -> ClockProfile:
    """Build the command minima at `tck_ps`.

    `cl` selects RL/WL. When it is omitted, the fastest CL whose tCK minimum
    is no faster than this clock is used (CL=11 at 1.25 ns, CL=3 at 5 ns).
    """
    if tck_ps <= 0:
        raise ValueError(tck_ps)
    allowed = tuple(code for code, minimum in CL_MIN_TCK_PS.items() if tck_ps >= minimum)
    if not allowed:
        raise ValueError(f"tCK {tck_ps} ps is faster than every Table 11-3 column")
    if cl is None:
        # Slowest listed bin this clock still meets. 5 ns selects CL=3
        # (tCK min 4 ns). 1.25 ns selects CL=11.
        cl = max(allowed, key=lambda code: CL_MIN_TCK_PS[code])
    if cl not in allowed:
        raise ValueError(f"CL={cl} is faster than tCK={tck_ps} ps allows: {allowed}")
    twr = cycles(15_000, tck_ps)
    nwr_min = min(code for code in ALLOWED_NWR if code >= twr)
    return ClockProfile(
        tck_ps=tck_ps,
        CL=cl,
        AL=P.AL,
        RL=P.AL + cl,
        WL=P.AL + cl,
        tRCD=cycles(13_750, tck_ps),
        tRP=cycles(13_750, tck_ps),
        tRAS=cycles(35_000, tck_ps),
        tRC=cycles(48_750, tck_ps),
        tRRD=cycles(7_500, tck_ps),
        tWR=twr,
        tPPD_ACT=P.tPPD_ACT,
        tPPD_IDLE=P.tPPD_IDLE,
        tMRD=P.tMRD,
        tMOD=max(12, cycles(15_000, tck_ps)),
        tRESET=cycles(5_000_000, tck_ps),
        tREFI_FST=cycles(100_000, tck_ps),
        tREFI_LP=cycles(3_200_000, tck_ps),
        tREF_BUSY_FST=cycles(100_000, tck_ps),
        tREF_BUSY_LP=cycles(3_200_000, tck_ps),
        tRTW=0 if cl == 3 else P.tRTW,
        tWTR=0 if cl == 3 else P.tWTR,
        tCKSPE=P.tCKSPE,
        tCKSPX=P.tCKSPX,
        tZQINIT=cycles(2_000_000, tck_ps),
        tZQCL=cycles(360_000, tck_ps),
        tZQCS=cycles(90_000, tck_ps),
        tZQRESET=cycles(50_000, tck_ps),
        word_clocks=P.word_clocks,
        nWR_MIN=nwr_min,
        allowed_cl=allowed,
    )


def matches_speed_1600(prof: ClockProfile) -> bool:
    return (
        prof.tck_ps == P.tCK_ps
        and prof.CL == P.CL
        and prof.RL == P.RL
        and prof.tRCD == P.tRCD
        and prof.tRP == P.tRP
        and prof.tRAS == P.tRAS
        and prof.tRC == P.tRC
        and prof.tRRD == P.tRRD
        and prof.tWR == P.tWR
        and prof.tMOD == P.tMOD
        and prof.tRESET == P.tRESET
        and prof.tREF_BUSY_FST == P.tREF_BUSY_FST
        and prof.tZQINIT == P.tZQINIT
        and prof.nWR_MIN == P.nWR_MIN
        and prof.allowed_cl == (11,)
    )
