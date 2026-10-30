"""Command-level timing and functional model of one EM6GA16L RPC DRAM.

The caller presents one command at an integer cycle. The cycle is the CK edge
on which the parallel request packet is decoded, not the earlier STB-low edge
(Section 3.3: STB falls two clocks before the packet).

An early or illegal command appends a violation and does not change bank
state or the array. It is not moved to a later legal cycle.
"""

from __future__ import annotations

from dataclasses import dataclass

from .params import ALLOWED_NWR, GEOMETRY, P, burst_clocks

ENFORCED_CONSTRAINTS = frozenset(
    {
        "tRCD",
        "tRP",
        "tRAS",
        "tRC",
        "tRRD",
        "tWR",
        "nWR",
        "tWTR",
        "tRTW",
        "tPPD",
        "tPPD_grid",
        "tCCD",
        "tMRD",
        "tMOD",
        "tRESET",
        "tREFI",
        "tCKSPE",
        "tCKSPX",
        "tZQINIT",
        "tZQCL",
        "tZQCS",
        "tZQRESET",
        "read_to_precharge",
        "monotonic",
        "cycle",
        "address",
        "burst_count",
        "burst_data",
        "mask",
        "row_open",
        "row_mismatch",
        "require_idle_bank",
        "require_active_bank",
        "require_all_idle",
        "init_reset",
        "init_precharge",
        "init_mrs",
        "CL",
        "REFOP",
        "CSRFX",
        "zout",
        "zq_kind",
        "opcode",
        "refresh_mode",
        "refresh_busy",
        "auto_precharge_pending",
    }
)

@dataclass(frozen=True, slots=True)
class Violation:
    constraint: str
    offered_cycle: int
    earliest_legal_cycle: int | None
    detail: str = ""

    def __str__(self) -> str:
        return (
            f"{self.constraint} offered={self.offered_cycle} "
            f"earliest={self.earliest_legal_cycle} {self.detail}"
        ).rstrip()


@dataclass(frozen=True, slots=True)
class IssueResult:
    accepted: bool
    offered_cycle: int
    data: bytes | None = None
    data_cycle: int | None = None
    violations: tuple[Violation, ...] = ()


@dataclass(frozen=True, slots=True)
class Command:
    kind: str
    cycle: int
    bank: int | None = None
    row: int | None = None
    column: int = 0
    burst_count: int = 0
    data: bytes | None = None
    first_mask: int = 0
    last_mask: int = 0
    auto_precharge: bool = False
    all_banks: bool = False
    banks: tuple[int, ...] | None = None
    cl: int = P.CL
    nwr: int = P.nWR_MIN
    csrfx: int = 0
    refop: int | None = None
    zout: int = 1
    zq: str = "init"


def Activate(cycle: int, bank: int, row: int) -> Command:
    return Command("activate", cycle, bank=bank, row=row)


def Precharge(cycle: int, bank: int | None = None, *, all_banks: bool = False) -> Command:
    return Command("precharge", cycle, bank=bank, all_banks=all_banks)


def Read(
    cycle: int,
    bank: int,
    column: int,
    *,
    burst_count: int = 0,
    row: int | None = None,
    auto_precharge: bool = False,
) -> Command:
    return Command(
        "read",
        cycle,
        bank=bank,
        column=column,
        burst_count=burst_count,
        row=row,
        auto_precharge=auto_precharge,
    )


def Write(
    cycle: int,
    bank: int,
    column: int,
    data: bytes,
    *,
    burst_count: int = 0,
    first_mask: int = 0,
    last_mask: int = 0,
    row: int | None = None,
    auto_precharge: bool = False,
) -> Command:
    return Command(
        "write",
        cycle,
        bank=bank,
        column=column,
        data=data,
        burst_count=burst_count,
        first_mask=first_mask,
        last_mask=last_mask,
        row=row,
        auto_precharge=auto_precharge,
    )


def Refresh(
    cycle: int,
    banks: tuple[int, ...] = (0, 1, 2, 3),
    refop: int | None = None,
) -> Command:
    return Command("refresh", cycle, banks=banks, refop=refop)


def RefreshExit(cycle: int) -> Command:
    return Command("refresh_exit", cycle)


def ModeRegister(
    cycle: int,
    *,
    cl: int = P.CL,
    nwr: int = P.nWR_MIN,
    csrfx: int = 0,
    refop: int = 0,
    zout: int = 1,
) -> Command:
    return Command("mrs", cycle, cl=cl, nwr=nwr, csrfx=csrfx, refop=refop, zout=zout)


def Reset(cycle: int) -> Command:
    return Command("reset", cycle)


def ZqCal(cycle: int, kind: str = "init") -> Command:
    return Command("zq", cycle, zq=kind)


@dataclass
class _Bank:
    row: int | None = None
    act_cycle: int | None = None
    last_act_cycle: int | None = None
    pre_cycle: int | None = None
    ap_cycle: int | None = None
    last_read: tuple[int, int] | None = None
    last_write: tuple[int, int] | None = None


class RpcDram:
    """One EM6GA16L device at speed-1600.

    `page_policy` is recorded configuration. A row is precharged after a burst
    only when that command sets `auto_precharge=True`. Open-page and
    closed-page do not precharge on their own.
    """

    def __init__(
        self,
        page_policy: str = "open",
        timing=None,
        refresh_occupancy: str = "one_trefi",
        loop_finish: str = "unspecified",
    ) -> None:
        if page_policy not in ("open", "closed"):
            raise ValueError(page_policy)
        if refresh_occupancy not in ("one_trefi", "row_step"):
            raise ValueError(refresh_occupancy)
        if loop_finish not in ("unspecified", "row_step"):
            raise ValueError(loop_finish)
        self.page_policy = page_policy
        self.refresh_occupancy = refresh_occupancy
        self.loop_finish = loop_finish
        # P is the speed-1600 column from the isolated model. Callers that
        # pass timing= use the same checks at another tCK.
        self.p = P if timing is None else timing
        self.mem = bytearray(GEOMETRY.banks * GEOMETRY.rows * GEOMETRY.columns * GEOMETRY.word_bytes)
        self.banks = [_Bank() for _ in range(GEOMETRY.banks)]
        self.violations: list[Violation] = []
        self.phase = "powerup"
        self.last_offered: int | None = None
        self.last_cmd_cycle: int | None = None
        self.last_act_cycle: int | None = None
        self.last_col: tuple[str, int, int] | None = None
        self.busy_until: int | None = None
        self.busy_name: str | None = None
        self.busy_detail = ""
        self.in_loop = False
        self.loop_ref_cycle: int | None = None
        self.mrs_cycle: int | None = None
        self.cl: int | None = None
        self.nwr: int | None = None
        self.csrfx = 0
        self.refop = 0
        self.zout = 0
        self.last_refresh_banks: tuple[int, ...] = ()

    def initialize(
        self,
        start: int = 0,
        *,
        cl: int = P.CL,
        nwr: int = P.nWR_MIN,
        csrfx: int = 0,
        refop: int = 0,
        zout: int = 1,
    ) -> int:
        """Reset, precharge-all, MRS. Return the first cycle a memory command is legal.

        Cycle 0 is after the Section 4 200 us clock-stable wait. ZQ calibration
        is not required here; issue `ZqCal` if the quiet window must be modeled.
        """
        pre_at = start + self.p.tRESET
        # tRP and idle tPPD both apply. At speed-1600, tRP is the larger one.
        mrs_at = pre_at + max(self.p.tRP, self.p.tPPD_IDLE)
        steps = (
            ("reset", Reset(start)),
            ("precharge", Precharge(pre_at, all_banks=True)),
            (
                "mrs",
                ModeRegister(
                    mrs_at,
                    cl=cl,
                    nwr=nwr,
                    csrfx=csrfx,
                    refop=refop,
                    zout=zout,
                ),
            ),
        )
        for name, cmd in steps:
            result = self.issue(cmd)
            if not result.accepted:
                raise RuntimeError(f"initialize {name} rejected: {result.violations}")
        return steps[-1][1].cycle + self.p.tMOD

    def bank_row(self, bank: int) -> int | None:
        return self.banks[bank].row

    def issue(self, command: Command) -> IssueResult:
        viol: list[Violation] = []

        def bad(name: str, earliest: int | None, detail: str = "") -> None:
            viol.append(Violation(name, command.cycle, earliest, detail))

        if command.cycle < 0:
            bad("cycle", 0, "cycle is an integer tCK index and must be >= 0")
            return self._reject(command, viol)
        if self.last_offered is not None and command.cycle < self.last_offered:
            bad("monotonic", self.last_offered, "commands are not reordered or delayed")
            return self._reject(command, viol)
        self.last_offered = command.cycle
        self._apply_auto_precharge(command.cycle)

        if self.in_loop:
            return self._during_loop(command, viol, bad)
        if self.busy_until is not None and command.cycle < self.busy_until:
            bad(self.busy_name or "busy", self.busy_until, self.busy_detail)
            return self._reject(command, viol)
        self._release_busy()

        if command.kind == "reset":
            self._commit_reset(command)
            return self._accept(command, None, None)

        if self.phase != "ready":
            return self._during_init(command, viol, bad)

        self._ready_checks(command, bad)
        if viol:
            return self._reject(command, viol)
        data, data_cycle = self._commit(command)
        return self._accept(command, data, data_cycle)

    def _reject(self, command: Command, viol: list[Violation]) -> IssueResult:
        self.violations.extend(viol)
        return IssueResult(False, command.cycle, None, None, tuple(viol))

    def _accept(self, command: Command, data: bytes | None, data_cycle: int | None) -> IssueResult:
        return IssueResult(True, command.cycle, data, data_cycle, ())

    def _release_busy(self) -> None:
        if self.busy_until is None:
            return
        self.busy_until = None
        self.busy_name = None
        self.busy_detail = ""
        if self.phase == "reset":
            self.phase = "need_pre"

    def _during_loop(self, cmd: Command, viol: list[Violation], bad) -> IssueResult:
        assert self.loop_ref_cycle is not None
        if cmd.kind == "refresh_exit":
            earliest = self.loop_ref_cycle + self.p.tCKSPE
            if cmd.cycle < earliest:
                bad("tCKSPE", earliest, "loop refresh exit")
                return self._reject(cmd, viol)
            self.in_loop = False
            self.loop_ref_cycle = None
            tail = self._loop_tail()
            self.busy_until = cmd.cycle + self.p.tCKSPX + tail
            self.busy_name = "tCKSPX" if tail == 0 else "tREFI"
            self.busy_detail = (
                "clocks required before refresh exit completes"
                if tail == 0
                else f"exit plus inferred finish of the current bank loop ({tail} cycles)"
            )
            self.last_cmd_cycle = cmd.cycle
            return self._accept(cmd, None, None)
        earliest = self.loop_ref_cycle + self.p.tCKSPE + self.p.tCKSPX
        bad(
            "refresh_busy",
            earliest,
            "loop refresh holds the device until refresh_exit, then tCKSPX",
        )
        return self._reject(cmd, viol)

    def _during_init(self, cmd: Command, viol: list[Violation], bad) -> IssueResult:
        if self.phase == "powerup":
            bad("init_reset", None, "reset is required before any other command")
            return self._reject(cmd, viol)
        if self.phase == "need_pre":
            if cmd.kind != "precharge" or not cmd.all_banks:
                bad("init_precharge", None, "Section 4 precharge-all after reset, before MRS")
                return self._reject(cmd, viol)
            self._check_ppd(cmd, bad)
            if viol:
                return self._reject(cmd, viol)
            for bank in self.banks:
                self._close_bank(bank, cmd.cycle)
            self.phase = "need_mrs"
            self.last_cmd_cycle = cmd.cycle
            return self._accept(cmd, None, None)
        if self.phase == "need_mrs":
            if cmd.kind != "mrs":
                bad("init_mrs", None, "MRS is required after precharge-all and tRP")
                return self._reject(cmd, viol)
            self._check_ppd(cmd, bad)
            self._check_trp_all(cmd, bad)
            self._check_mrs_fields(cmd, bad)
            if viol:
                return self._reject(cmd, viol)
            self._commit_mrs(cmd)
            return self._accept(cmd, None, None)
        bad("opcode", None, f"unhandled phase {self.phase}")
        return self._reject(cmd, viol)

    def _ready_checks(self, cmd: Command, bad) -> None:
        self._check_ppd(cmd, bad)
        if cmd.kind == "mrs":
            self._check_tmrd(cmd, bad)
        else:
            self._check_tmod(cmd, bad)
        if cmd.kind == "activate":
            self._check_activate(cmd, bad)
        elif cmd.kind == "precharge":
            self._check_precharge(cmd, bad)
        elif cmd.kind in ("read", "write"):
            self._check_column(cmd, bad)
        elif cmd.kind == "refresh":
            self._check_refresh(cmd, bad)
        elif cmd.kind == "mrs":
            self._check_mrs_cmd(cmd, bad)
        elif cmd.kind == "zq":
            self._check_zq(cmd, bad)
        elif cmd.kind == "refresh_exit":
            bad("refresh_mode", None, "refresh_exit applies only to loop refresh (CSRFX=1)")
        else:
            bad("opcode", None, f"unknown command {cmd.kind}")

    def _commit(self, cmd: Command) -> tuple[bytes | None, int | None]:
        if cmd.kind == "activate":
            bank = self.banks[cmd.bank]
            bank.row = cmd.row
            bank.act_cycle = cmd.cycle
            bank.last_act_cycle = cmd.cycle
            bank.ap_cycle = None
            bank.last_read = None
            bank.last_write = None
            self.last_act_cycle = cmd.cycle
            self.last_cmd_cycle = cmd.cycle
            return None, None
        if cmd.kind == "precharge":
            for index in self._targets(cmd):
                self._close_bank(self.banks[index], cmd.cycle)
            self.last_cmd_cycle = cmd.cycle
            return None, None
        if cmd.kind == "read":
            data = self._transfer(cmd, write=False)
            self._note_column(cmd, "read")
            return data, cmd.cycle + self.p.RL
        if cmd.kind == "write":
            self._transfer(cmd, write=True)
            self._note_column(cmd, "write")
            return None, cmd.cycle + self.p.WL
        if cmd.kind == "refresh":
            refop = self.refop if cmd.refop is None else cmd.refop
            banks = cmd.banks if cmd.banks is not None else (0, 1, 2, 3)
            for bank in self.banks:
                self._close_bank(bank, cmd.cycle)
            self.last_refresh_banks = tuple(banks)
            self.last_col = None
            self.last_cmd_cycle = cmd.cycle
            if self.csrfx == 1:
                self.in_loop = True
                self.loop_ref_cycle = cmd.cycle
            else:
                window = self.refresh_window(refop, len(tuple(banks)))
                self.busy_until = cmd.cycle + window
                self.busy_name = "tREFI"
                self.busy_detail = (
                    f"{self.refresh_occupancy} one-shot busy window "
                    f"({window} cycles, {len(tuple(banks))} banks)"
                )
            return None, None
        if cmd.kind == "mrs":
            self._commit_mrs(cmd)
            return None, None
        if cmd.kind == "zq":
            name, cycles = self._zq_entry(cmd.zq)
            self.busy_until = cmd.cycle + cycles
            self.busy_name = name
            self.busy_detail = f"{cmd.zq} ZQ calibration"
            self.last_cmd_cycle = cmd.cycle
            return None, None
        raise RuntimeError(cmd.kind)

    def _note_column(self, cmd: Command, kind: str) -> None:
        bl = burst_clocks(cmd.burst_count, self.p.word_clocks)
        bank = self.banks[cmd.bank]
        if kind == "read":
            bank.last_read = (cmd.cycle, bl)
        else:
            bank.last_write = (cmd.cycle, bl)
        self.last_col = (kind, cmd.cycle, bl)
        self.last_cmd_cycle = cmd.cycle
        if cmd.auto_precharge:
            bounds = self._row_bounds(bank)
            bank.ap_cycle = max(earliest for _, earliest in bounds)

    def _commit_reset(self, cmd: Command) -> None:
        self.banks = [_Bank() for _ in range(GEOMETRY.banks)]
        self.phase = "reset"
        self.in_loop = False
        self.loop_ref_cycle = None
        self.cl = None
        self.nwr = None
        self.csrfx = 0
        self.refop = 0
        self.zout = 0
        self.mrs_cycle = None
        self.last_col = None
        self.last_act_cycle = None
        self.last_cmd_cycle = cmd.cycle
        self.busy_until = cmd.cycle + self.p.tRESET
        self.busy_name = "tRESET"
        self.busy_detail = "reset exit"

    def _commit_mrs(self, cmd: Command) -> None:
        self.cl = cmd.cl
        self.nwr = cmd.nwr
        self.csrfx = cmd.csrfx
        self.refop = 0 if cmd.refop is None else cmd.refop
        self.zout = cmd.zout
        self.mrs_cycle = cmd.cycle
        self.phase = "ready"
        self.last_cmd_cycle = cmd.cycle


    def refresh_window(self, refop: int, n_banks: int) -> int:
        """Cycles the device stays busy after a one-shot REF.

        ``one_trefi`` is the earlier reading: the busy window is one tREFI.
        ``row_step`` is the Section 5 reading: one command burst-refreshes
        every row of every selected bank, and tREFI is the step. The product
        is not printed as a single AC parameter.
        """
        step = self.p.tREF_BUSY_LP if refop == 1 else self.p.tREF_BUSY_FST
        if n_banks < 1:
            return step
        if self.refresh_occupancy == "row_step":
            return GEOMETRY.rows * step * n_banks
        return step

    def _loop_tail(self) -> int:
        """Section 5.2: after the exit pulse the device finishes the current
        bank loop. That tail has no AC number. ``row_step`` uses the same
        inferred product as one-shot refresh. ``unspecified`` adds nothing.
        """
        if self.loop_finish != "row_step":
            return 0
        n_banks = len(self.last_refresh_banks) or GEOMETRY.banks
        step = self.p.tREF_BUSY_LP if self.refop == 1 else self.p.tREF_BUSY_FST
        return GEOMETRY.rows * step * n_banks

    def _zq_entry(self, kind: str) -> tuple[str, int]:
        table = {
            "init": ("tZQINIT", self.p.tZQINIT),
            "long": ("tZQCL", self.p.tZQCL),
            "short": ("tZQCS", self.p.tZQCS),
            "reset": ("tZQRESET", self.p.tZQRESET),
        }
        return table[kind]

    def _turnaround(self) -> int:
        """Table 11-3: CL=3 has no bubble; CL=8 and CL=10 to 11 wait 8 tCK."""
        cl = self.cl if self.cl is not None else self.p.CL
        return 0 if cl == 3 else 8

    def _check_ppd(self, cmd: Command, bad) -> None:
        if self.last_cmd_cycle is None:
            return
        active = any(bank.row is not None for bank in self.banks)
        gap = self.p.tPPD_ACT if active else self.p.tPPD_IDLE
        earliest = self.last_cmd_cycle + gap
        if cmd.cycle < earliest:
            state = "activate" if active else "idle"
            bad("tPPD", earliest, f"{state}-state spacing is {gap} tCK")
        elif active and (cmd.cycle - self.last_cmd_cycle) % gap:
            slots = (cmd.cycle - self.last_cmd_cycle + gap - 1) // gap
            bad("tPPD_grid", self.last_cmd_cycle + slots * gap,
                f"active-state parallel commands must be {gap} tCK apart or a multiple")

    def _check_tmod(self, cmd: Command, bad) -> None:
        if self.mrs_cycle is not None and cmd.cycle < self.mrs_cycle + self.p.tMOD:
            bad("tMOD", self.mrs_cycle + self.p.tMOD, "MRS update delay before a non-MRS command")

    def _check_tmrd(self, cmd: Command, bad) -> None:
        if self.mrs_cycle is not None and cmd.cycle < self.mrs_cycle + self.p.tMRD:
            bad("tMRD", self.mrs_cycle + self.p.tMRD, "MRS to MRS")

    def _check_trp_all(self, cmd: Command, bad) -> None:
        earliest = None
        for bank in self.banks:
            if bank.pre_cycle is None:
                continue
            candidate = bank.pre_cycle + self.p.tRP
            if earliest is None or candidate > earliest:
                earliest = candidate
        if earliest is not None and cmd.cycle < earliest:
            bad("tRP", earliest, "precharge recovery")

    def _check_mrs_fields(self, cmd: Command, bad) -> None:
        allowed = getattr(self.p, "allowed_cl", (self.p.CL,))
        if cmd.cl not in allowed:
            bad("CL", None, f"CL={cmd.cl} is not legal at this clock; allowed {allowed}")
        if cmd.nwr not in ALLOWED_NWR:
            bad("nWR", None, f"nWR {cmd.nwr} is not a Table 7-2 code")
        elif cmd.nwr < self.p.tWR:
            bad("nWR", None, f"nWR {cmd.nwr} is below tWR={self.p.tWR} cycles at 1.25 ns")
        if cmd.refop not in (0, 1):
            bad("REFOP", None, "REFOP encodings 10 and 11 are reserved")
        if cmd.csrfx not in (0, 1):
            bad("CSRFX", None, "CSRFX is 0 (one-shot) or 1 (loop)")
        if not 0 <= cmd.zout <= 15:
            bad("zout", None, "Zout is the 4-bit MRS field")

    def _check_activate(self, cmd: Command, bad) -> None:
        bank_ok = self._bank_ok(cmd.bank, bad)
        row_ok = cmd.row is not None and 0 <= cmd.row < GEOMETRY.rows
        if bank_ok and not row_ok:
            bad("address", None, "row")
        if not bank_ok or not row_ok:
            return
        if self.last_act_cycle is not None and cmd.cycle < self.last_act_cycle + self.p.tRRD:
            bad("tRRD", self.last_act_cycle + self.p.tRRD, "ACT to ACT")
        bank = self.banks[cmd.bank]
        if bank.row is not None:
            bad("require_idle_bank", None, f"bank {cmd.bank} already has row {bank.row} open")
            return
        if bank.pre_cycle is not None and cmd.cycle < bank.pre_cycle + self.p.tRP:
            bad("tRP", bank.pre_cycle + self.p.tRP, f"bank {cmd.bank}")
        if bank.last_act_cycle is not None and cmd.cycle < bank.last_act_cycle + self.p.tRC:
            bad("tRC", bank.last_act_cycle + self.p.tRC, f"bank {cmd.bank}")

    def _check_precharge(self, cmd: Command, bad) -> None:
        targets = self._targets(cmd, bad)
        if targets is None:
            return
        for index in targets:
            bank = self.banks[index]
            if bank.row is None:
                bad("require_active_bank", None, f"bank {index} is already precharged")
                continue
            for name, earliest in self._row_bounds(bank):
                if cmd.cycle < earliest:
                    bad(name, earliest, f"bank {index}")

    def _check_column(self, cmd: Command, bad) -> None:
        if not self._bank_ok(cmd.bank, bad):
            return
        if not 0 <= cmd.column < GEOMETRY.columns:
            bad("address", None, "column")
            return
        if not 0 <= cmd.burst_count <= 63:
            bad("burst_count", None, "BC[0:5] is 0..63 (1..64 WORDs)")
            return
        bank = self.banks[cmd.bank]
        if bank.row is None:
            bad("row_open", None, f"bank {cmd.bank} is precharged")
            return
        if cmd.cycle < bank.act_cycle + self.p.tRCD:
            bad("tRCD", bank.act_cycle + self.p.tRCD, f"bank {cmd.bank}")
        if cmd.row is not None:
            if not 0 <= cmd.row < GEOMETRY.rows:
                bad("address", None, "row")
            elif cmd.row != bank.row:
                bad("row_mismatch", None, f"open row is {bank.row}")
        if bank.ap_cycle is not None:
            bad("auto_precharge_pending", None, f"bank {cmd.bank} closes at cycle {bank.ap_cycle}")
        if self.last_col is not None:
            kind, cycle, clocks = self.last_col
            if cmd.cycle < cycle + clocks:
                bad("tCCD", cycle + clocks, "previous WORD burst still occupies the bus")
            turn = self._turnaround()
            if kind == "write" and cmd.kind == "read" and cmd.cycle < cycle + turn:
                bad("tWTR", cycle + turn, "write burst to read burst")
            if kind == "read" and cmd.kind == "write" and cmd.cycle < cycle + turn:
                bad("tRTW", cycle + turn, "read burst to write burst")
        if cmd.kind == "read" and self.zout == 0:
            bad("zout", None, "MRS default Zout=open drives no read data (Section 2.13)")
        if cmd.kind == "write":
            need = (cmd.burst_count + 1) * GEOMETRY.word_bytes
            if cmd.data is None or len(cmd.data) != need:
                bad("burst_data", None, f"write data must be {need} bytes")
            self._check_mask(cmd.first_mask, bad, "first_mask")
            self._check_mask(cmd.last_mask, bad, "last_mask")

    def _check_refresh(self, cmd: Command, bad) -> None:
        banks = cmd.banks if cmd.banks is not None else (0, 1, 2, 3)
        if len(banks) == 0 or any(not 0 <= b < GEOMETRY.banks for b in banks):
            bad("address", None, "refresh bank select")
            return
        refop = self.refop if cmd.refop is None else cmd.refop
        if refop not in (0, 1):
            bad("REFOP", None, "REFOP encodings 10 and 11 are reserved")
        for index, bank in enumerate(self.banks):
            if bank.row is not None:
                if bank.last_act_cycle is not None and cmd.cycle < bank.last_act_cycle + self.p.tRC:
                    bad("tRC", bank.last_act_cycle + self.p.tRC, f"bank {index} ACT to REF")
                self._emit_recovery(cmd, bank, bad, include_tras=False)
            else:
                if bank.pre_cycle is not None and cmd.cycle < bank.pre_cycle + self.p.tRP:
                    bad("tRP", bank.pre_cycle + self.p.tRP, f"bank {index}")
                if bank.last_act_cycle is not None and cmd.cycle < bank.last_act_cycle + self.p.tRC:
                    bad("tRC", bank.last_act_cycle + self.p.tRC, f"bank {index}")

    def _check_mrs_cmd(self, cmd: Command, bad) -> None:
        self._require_all_idle(cmd, bad)
        if any(bank.row is not None for bank in self.banks):
            return
        self._check_trp_all(cmd, bad)
        self._check_mrs_fields(cmd, bad)

    def _check_zq(self, cmd: Command, bad) -> None:
        if cmd.zq not in ("init", "long", "short", "reset"):
            bad("zq_kind", None, "ZQ kind is init, long, short, or reset")
            return
        self._require_all_idle(cmd, bad)
        if any(bank.row is not None for bank in self.banks):
            return
        self._check_trp_all(cmd, bad)

    def _require_all_idle(self, cmd: Command, bad) -> None:
        for index, bank in enumerate(self.banks):
            if bank.row is not None:
                bad("require_all_idle", None, f"bank {index} is active")

    def _emit_recovery(self, cmd: Command, bank: _Bank, bad, *, include_tras: bool) -> None:
        for name, earliest in self._row_bounds(bank):
            if name == "tRAS" and not include_tras:
                continue
            if cmd.cycle < earliest:
                bad(name, earliest, "refresh precharges before the array operation")

    def _row_bounds(self, bank: _Bank) -> list[tuple[str, int]]:
        bounds: list[tuple[str, int]] = []
        if bank.act_cycle is not None:
            bounds.append(("tRAS", bank.act_cycle + self.p.tRAS))
        if bank.last_write is not None:
            cycle, clocks = bank.last_write
            base = cycle + self.p.WL + clocks
            bounds.append(("tWR", base + self.p.tWR))
            programmed = self.nwr if self.nwr is not None else self.p.tWR
            if programmed > self.p.tWR:
                bounds.append(("nWR", base + programmed))
        if bank.last_read is not None:
            cycle, clocks = bank.last_read
            bounds.append(("read_to_precharge", cycle + self.p.RL + clocks))
        return bounds

    def _check_mask(self, mask: int, bad, label: str) -> None:
        if mask < 0 or mask > 0xFFFFFFFF:
            bad("mask", None, f"{label} is a 32-bit field")

    def _bank_ok(self, bank: int | None, bad) -> bool:
        if bank is None or not 0 <= bank < GEOMETRY.banks:
            bad("address", None, "bank")
            return False
        return True

    def _targets(self, cmd: Command, bad=None) -> list[int] | None:
        if cmd.all_banks:
            return list(range(GEOMETRY.banks))
        if not self._bank_ok(cmd.bank, bad if bad is not None else (lambda *a: None)):
            return None
        return [cmd.bank]

    def _apply_auto_precharge(self, cycle: int) -> None:
        for bank in self.banks:
            if bank.ap_cycle is not None and bank.ap_cycle <= cycle and bank.row is not None:
                self._close_bank(bank, bank.ap_cycle)

    def _close_bank(self, bank: _Bank, cycle: int) -> None:
        bank.row = None
        bank.act_cycle = None
        bank.ap_cycle = None
        bank.last_read = None
        bank.last_write = None
        bank.pre_cycle = cycle

    def _addr(self, bank: int, row: int, column: int) -> int:
        g = GEOMETRY
        return ((bank * g.rows + row) * g.columns + column) * g.word_bytes

    def _mask_for_word(self, index: int, count: int, first: int, last: int) -> int:
        # Section 2.7: bit 1 masks the byte (it is not written). A one-WORD
        # burst is both the first and the last WORD, so either mask can block it.
        if count == 1:
            return first | last
        if index == 0:
            return first
        if index == count - 1:
            return last
        return 0

    def _transfer(self, cmd: Command, *, write: bool) -> bytes | None:
        count = cmd.burst_count + 1
        row = self.banks[cmd.bank].row
        assert row is not None
        out = bytearray()
        for word in range(count):
            column = (cmd.column + word) % GEOMETRY.columns
            addr = self._addr(cmd.bank, row, column)
            if not write:
                out += self.mem[addr : addr + GEOMETRY.word_bytes]
                continue
            mask = self._mask_for_word(word, count, cmd.first_mask, cmd.last_mask)
            start = word * GEOMETRY.word_bytes
            chunk = cmd.data[start : start + GEOMETRY.word_bytes]
            for offset in range(GEOMETRY.word_bytes):
                if (mask >> offset) & 1:
                    continue
                self.mem[addr + offset] = chunk[offset]
        if write:
            return None
        return bytes(out)
