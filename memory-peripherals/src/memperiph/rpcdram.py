"""RPC DRAM device, packet encoding, and FASED-style scheduler.

Defaults follow Etron EM6GA16L 256 Mbit RPC DRAM, Rev 1.4, speed-1600
(CL = 11, tCK = 1.25 ns). A second profile matches the ETH Zurich
controller's 200 MHz PHY clock.

The host byte-address map matches the ETH ``rpc_cmd_fsm`` packing so a
controller trace and this model decode the same bank/row/column. The
datasheet defines the array geometry but not a host physical-address map.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .util import AxiRequest, Completion, SparseMem, Violation, ck_ceil


@dataclass(frozen=True)
class Param:
    name: str
    value: str
    unit: str
    source: str
    section: str
    kind: str
    notes: str


@dataclass
class RpcDramParams:
    """One 256 Mbit x16 RPC DRAM."""

    size_bytes: int = 32 * 1024 * 1024
    n_banks: int = 4
    n_rows: int = 4096
    page_bytes: int = 2048
    word_bytes: int = 32  # 16 DDR beats of 16 bits
    tck_ps: int = 1_250
    cl: int = 11
    al: int = 1
    tRCD_ps: int = 13_750
    tRP_ps: int = 13_750
    tRC_ps: int = 48_750
    tRAS_ps: int = 35_000
    tRRD_ps: int = 7_500
    tWR_ps: int = 15_000
    tREFI_fst_ps: int = 100_000
    tREFI_lp_ps: int = 3_200_000
    retention_ps: int = 64_000_000_000
    tRESET_ps: int = 5_000_000
    tPWR_clock_ps: int = 200_000_000
    tZQINIT_ps: int = 2_000_000
    tZQCL_ps: int = 360_000
    tZQCS_ps: int = 90_000
    tPPD_idle_ck: int = 4
    tPPD_act_ck: int = 8
    tMRD_ck: int = 4
    tMOD_ps: int = 15_000
    tRTW_ck: int = 8
    tWTR_ck: int = 8
    burst_ck_per_word: int = 8
    # Inferred: a read burst must finish before PRE of that bank. The
    # datasheet lists tWR but not tRTP.
    tRTP_is_burst_end: bool = True

    def __post_init__(self) -> None:
        expect = self.n_banks * self.n_rows * self.page_bytes
        if self.size_bytes != expect:
            raise ValueError(f"geometry {expect} bytes does not match size {self.size_bytes}")

    @property
    def rl_ck(self) -> int:
        # Datasheet MRS: RL = AL + CL, AL = 1, and WL = RL.
        return self.al + self.cl

    @property
    def wl_ck(self) -> int:
        return self.rl_ck

    @property
    def tRCD_ck(self) -> int:
        return ck_ceil(self.tRCD_ps, self.tck_ps)

    @property
    def act_to_cas_ck(self) -> int:
        gap = self.tPPD_act_ck
        return ((self.tRCD_ck + gap - 1) // gap) * gap

    @property
    def tRP_ck(self) -> int:
        return ck_ceil(self.tRP_ps, self.tck_ps)

    @property
    def tRC_ck(self) -> int:
        return ck_ceil(self.tRC_ps, self.tck_ps)

    @property
    def tRAS_ck(self) -> int:
        return ck_ceil(self.tRAS_ps, self.tck_ps)

    @property
    def tRRD_ck(self) -> int:
        return ck_ceil(self.tRRD_ps, self.tck_ps)

    @property
    def tWR_ck(self) -> int:
        return ck_ceil(self.tWR_ps, self.tck_ps)

    @property
    def tREFI_fst_ck(self) -> int:
        return ck_ceil(self.tREFI_fst_ps, self.tck_ps)

    @property
    def tMOD_ck(self) -> int:
        return max(12, ck_ceil(self.tMOD_ps, self.tck_ps))

    @property
    def tRESET_ck(self) -> int:
        return ck_ceil(self.tRESET_ps, self.tck_ps)

    @property
    def retention_ck(self) -> int:
        return ck_ceil(self.retention_ps, self.tck_ps)

    @property
    def tPWR_ck(self) -> int:
        return ck_ceil(self.tPWR_clock_ps, self.tck_ps)

    @property
    def tZQINIT_ck(self) -> int:
        return ck_ceil(self.tZQINIT_ps, self.tck_ps)

    def catalog(self) -> list[Param]:
        src = "Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024)"
        return [
            Param("n_banks", "4", "banks", src, "Table 1-2, p.5", "specified", "BA[1:0]."),
            Param("n_rows", "4096", "rows", src, "Table 1-2, p.5", "specified", "RA[11:0]."),
            Param("page_bytes", "2048", "B", src, "Table 1-2, p.5", "specified",
                  "Page size 2 KB. CA[9:0], CA[3:0] not applied because BL=16."),
            Param("word_bytes", "32", "B", src, "Fig 2-14, p.30", "specified",
                  "One word is 16 bus samples on the x16 DDR bus."),
            Param("tck_ps", "1250", "ps", src, "Table 11-3, p.59", "specified",
                  "Speed-1600, CL=11, 800 MHz, 1600 MT/s/pin."),
            Param("cl", "11", "CK", src, "Table 11-3, p.59", "specified",
                  "Required CL at 800 MHz. MRS default code is CL=8; the speed grade overrides it."),
            Param("al", "1", "CK", src, "Table 7-2, p.51", "specified", "RL = AL + CL with AL fixed at 1. WL = RL."),
            Param("tRCD_ps", "13750", "ps", src, "Table 11-3, p.59", "specified", "11 CK at 1.25 ns."),
            Param("tRP_ps", "13750", "ps", src, "Table 11-3, p.59", "specified", "PRE command period."),
            Param("tRC_ps", "48750", "ps", src, "Table 11-3, p.59", "specified", "ACT to ACT or REF, same bank."),
            Param("tRAS_ps", "35000", "ps", src, "Table 11-3, p.59", "specified", "ACT to PRE."),
            Param("tRRD_ps", "7500", "ps", src, "Table 11-3, p.59", "specified", "ACT to ACT, different banks."),
            Param("tWR_ps", "15000", "ps", src, "Table 11-3, p.59", "specified", "Write recovery before PRE."),
            Param("tREFI_fst_ps", "100000", "ps", src, "Table 11-3 / Table 7-5", "specified",
                  "Row period while the one-shot fast refresh state is running. Not a JEDEC command interval."),
            Param("tREFI_lp_ps", "3200000", "ps", src, "Table 7-5, p.52", "specified",
                  "Low-power refresh period. Four banks at this rate take on the order of 64 ms."),
            Param("retention_ps", "64000000000", "ps", src, "Section 5, p.44", "specified",
                  "64 ms at Tc <= 85 C. 32 ms above 85 C is not the default."),
            Param("tRESET_ps", "5000000", "ps", src, "Table 11-3, p.59", "specified", "tRESET minimum 5 us."),
            Param("tPWR_clock_ps", "200000000", "ps", src, "Section 4, p.42", "specified",
                  "CK stable at least 200 us with CS# and STB high before reset."),
            Param("tZQINIT_ps", "2000000", "ps", src, "Table 11-3, p.60", "specified", "Initialization ZQ calibration."),
            Param("tPPD_idle_ck", "4", "CK", src, "Table 11-3, p.59", "specified",
                  "Parallel-command spacing from the idle (all-bank precharged) state."),
            Param("tPPD_act_ck", "8", "CK", src, "Table 11-3, p.59", "specified",
                  "Parallel-command spacing once any row is open. Multiples of 8."),
            Param("tMOD", "max(12 CK, 15 ns)", "CK", src, "Table 11-3, p.59", "specified", "MRS update delay."),
            Param("bc_encoding", "n_words = BC + 1", "words", "Rev 1.4 Table 7-3 plus ETH timing FSM",
                  "Table 7-3, p.52; rpc_timing_fsm.sv", "inferred",
                  "The table lists BC 0..63. The minimum packet is 1 word, and the ETH countdown (BC<<3)+7 is 8 CK when BC=0. LiteDRAM documents the same +1. BC=0 therefore means one 32-byte word."),
            Param("tRTP", "end of read burst", "CK", src, "not listed in Table 11-3", "inferred",
                  "No tRTP number is published. PRE of the bank being read is refused until that read burst completes."),
            Param("addr_map", "byte[4:0] off, [10:5] col, [22:11] row, [24:23] bank",
                  "bits", "ETH rpc_cmd_fsm.sv ACT/RD packing", "controller address", "inferred",
                  "Chosen so this model and the ETH controller select the same bank and row. The datasheet does not define a host address map."),
            Param("refresh_duration", "n_rows * tREFI * n_selected_banks", "CK", src,
                  "Section 5, p.44-45", "inferred",
                  "One-shot refresh burst-refreshes every row of the selected banks, one row per tREFI, and the device is busy the whole time."),
        ]


def profile_1600() -> RpcDramParams:
    """Datasheet speed-1600. Peak pin bandwidth 3.2 GB/s."""
    return RpcDramParams()


def profile_200mhz() -> RpcDramParams:
    """ETH PHY clock and observed MRS: 200 MHz, CL=8, RL=9."""
    return RpcDramParams(tck_ps=5_000, cl=8, tRTW_ck=8, tWTR_ck=8)


@dataclass
class RpcCommand:
    op: str
    cycle: int
    bank: int = 0
    row: int = 0
    col: int = 0
    bc: int = 0
    mask: int = 0
    serial: bool = False
    data: bytes = b""
    enable: bytes = b""
    cl: int | None = None
    zout_open: bool = False
    ref_op: int = 0  # 0 fast, 1 low-power
    result: bytes = b""


@dataclass
class BankState:
    row: int | None = None
    act_cycle: int = -10**9
    pre_cycle: int = -10**9
    act_ok: int = 0
    pre_ok: int = 0


def decode_addr(addr: int, p: RpcDramParams | None = None) -> tuple[int, int, int, int]:
    """Return bank, row, column (CA[9:0]), byte offset within the 32 B word."""
    p = p or RpcDramParams()
    if addr < 0 or addr >= p.size_bytes:
        raise IndexError(f"address {addr:#x} outside RPC DRAM")
    off = addr & 31
    col_group = (addr >> 5) & 63
    row = (addr >> 11) & (p.n_rows - 1)
    bank = (addr >> 23) & (p.n_banks - 1)
    col = col_group << 4
    return bank, row, col, off


def flat_addr(bank: int, row: int, col: int, p: RpcDramParams | None = None) -> int:
    p = p or RpcDramParams()
    return bank * (p.n_rows * p.page_bytes) + row * p.page_bytes + col * 2


def encode_parallel(cmd: RpcCommand) -> tuple[int, int]:
    """Datasheet Table 7-1 / LiteDRAM DB beats. Returns (db_p, db_n)."""
    op = cmd.op
    if op == "ACT":
        db_p = 0b101 | ((cmd.bank & 3) << 3)
        db_n = (cmd.row & 0xFFF) << 1
        return db_p, db_n
    if op in ("RD", "WR"):
        opc = 0b000 if op == "RD" else 0b001
        ca4 = (cmd.col >> 4) & 7
        ca7 = (cmd.col >> 7) & 7
        db_p = opc | ((cmd.bank & 3) << 3) | ((cmd.bc & 63) << 5) | (ca4 << 13)
        db_n = ca7 << 13
        return db_p, db_n
    if op == "PRE":
        db_p = 0b100 | ((cmd.mask & 0xF) << 6)
        return db_p, 0
    if op == "REF":
        db_p = 0b110 | ((cmd.mask & 0xF) << 6)
        db_n = (cmd.ref_op & 3) << 1
        return db_p, db_n
    if op == "MRS":
        # CL in [5:3], opcode [2:0]=010. Only the fields this model uses.
        cl_code = {8: 0b000, 10: 0b001, 11: 0b010, 3: 0b110}[cmd.cl if cmd.cl else 8]
        db_p = 0b010 | (cl_code << 3)
        return db_p, 0
    if op == "RESET":
        return 0, 1
    raise ValueError(f"no parallel encoding for {op}")


def encode_eth_word(cmd: RpcCommand) -> int:
    """32-bit PHY command word used by the ETH rpc_cmd_fsm / rpc_cmd_decoder."""
    if cmd.op == "ACT":
        return ((cmd.bank & 3) << 19) | (0b101 << 16) | ((cmd.row & 0xFFF) << 1)
    if cmd.op in ("RD", "WR"):
        opc = 0b000 if cmd.op == "RD" else 0b001
        col_group = (cmd.col >> 4) & 63
        ca4 = col_group & 7
        ca7 = (col_group >> 3) & 7
        return (
            (ca4 << 29)
            | ((cmd.bc & 63) << 21)
            | ((cmd.bank & 3) << 19)
            | (opc << 16)
            | (ca7 << 13)
        )
    if cmd.op == "PRE":
        return ((cmd.mask & 0xF) << 22) | (0b100 << 16)
    if cmd.op == "REF":
        return ((cmd.mask & 0xF) << 22) | (0b110 << 16)
    if cmd.op == "ZQC":
        return (0b001 << 16) | 1
    if cmd.op == "RESET":
        return 1
    raise ValueError(cmd.op)


class RpcDramDevice:
    """Command-level RPC DRAM. Checks timing and updates an array."""

    def __init__(self, params: RpcDramParams | None = None, *,
                 assume_initialized: bool = False):
        self.p = params or RpcDramParams()
        self.mem = SparseMem(self.p.size_bytes)
        self.banks = [BankState() for _ in range(self.p.n_banks)]
        self.violations: list[Violation] = []
        self.commands: list[RpcCommand] = []
        self.cycle = 0
        self.cl = self.p.cl
        self.zout_open = True
        self.initialized = False
        self.last_parallel: int | None = None
        self.last_act = -10**9
        self.in_burst = False
        self.burst_anchor = 0
        self.burst_dir: str | None = None
        self.burst_bank: int | None = None
        self.data_until = 0
        self.busy_until = 0
        self.burst_data_end = 0
        if assume_initialized:
            self.initialized = True
            self.zout_open = False
            self.cl = self.p.cl

    @property
    def rl(self) -> int:
        return self.p.al + self.cl

    @property
    def wl(self) -> int:
        return self.rl

    def all_precharged(self) -> bool:
        return all(b.row is None for b in self.banks)

    def tppd(self) -> int:
        return self.p.tPPD_idle_ck if self.all_precharged() else self.p.tPPD_act_ck

    def issue(self, cmd: RpcCommand) -> RpcCommand:
        self._catch_up(cmd.cycle)
        before = len(self.violations)
        self._check(cmd)
        if len(self.violations) == before:
            self._apply(cmd)
            self.cycle = cmd.cycle
        self.commands.append(cmd)
        return cmd

    def initialize(self) -> int:
        """Datasheet section 4 power-up. Returns the first cycle a user command is legal."""
        self.__init__(self.p, assume_initialized=False)
        t = self.p.tPWR_ck + self.p.tRESET_ck
        self.initialized = True  # reset has completed; Zout still open
        self.issue(RpcCommand("PRE", t, mask=0xF))
        mrs = max(t + self.p.tRP_ck, t + self.tppd())
        # tPPD after PRE: all banks are precharged once PRE is applied, so the
        # gap is measured from the PRE cycle using the post-PRE state inside
        # the next check. Force the MRS onto a legal cycle by retrying.
        mrs = self._earliest_after(mrs)
        self.issue(RpcCommand("MRS", mrs, cl=self.p.cl, zout_open=False))
        zq = mrs + self.p.tMOD_ck
        zq = self._earliest_after(zq)
        self.issue(RpcCommand("ZQC", zq))
        self.busy_until = zq + self.p.tZQINIT_ck
        self.cycle = self.busy_until
        return self.busy_until

    def _earliest_after(self, target: int) -> int:
        if self.last_parallel is None:
            return target
        return max(target, self.last_parallel + self.tppd())

    def _catch_up(self, cycle: int) -> None:
        if self.in_burst and cycle >= self.burst_data_end:
            self.in_burst = False
            self.burst_dir = None
            self.burst_bank = None

    def _check(self, cmd: RpcCommand) -> None:
        if cmd.cycle < self.cycle:
            self._bad(cmd, "time-reversal", "command moves backwards")
            return
        if cmd.op != "RESET" and not self.initialized and cmd.op != "PRE":
            # PRE is the first command of init, which sets initialized before PRE.
            pass
        if cmd.cycle < self.busy_until and cmd.op not in ("RESET",):
            self._bad(cmd, "busy", f"device busy until {self.busy_until}")
        if cmd.serial:
            if not self.in_burst:
                self._bad(cmd, "serial-idle", "serial command while not bursting")
            elif (cmd.cycle - self.burst_anchor) % 8 != 0 or cmd.cycle == self.burst_anchor:
                self._bad(cmd, "serial-grid", "serial command is not on the 8 CK grid")
        else:
            if self.in_burst and cmd.op != "BST":
                self._bad(cmd, "burst-open", "parallel command while a burst is open")
            if self.last_parallel is not None and cmd.op != "BST":
                need = self.tppd()
                if cmd.cycle < self.last_parallel + need:
                    self._bad(cmd, "tPPD", f"need {need} CK, got {cmd.cycle - self.last_parallel}")
                elif not self.all_precharged() and (
                    cmd.cycle - self.last_parallel
                ) % self.p.tPPD_act_ck:
                    self._bad(cmd, "tPPD-grid", "active-state parallel commands use 8-CK slots")
        if cmd.op == "ACT":
            self._check_act(cmd)
        elif cmd.op == "PRE":
            self._check_pre(cmd)
        elif cmd.op in ("RD", "WR"):
            self._check_cas(cmd)
        elif cmd.op == "REF":
            self._check_ref(cmd)
        elif cmd.op == "MRS":
            if not self.all_precharged():
                self._bad(cmd, "mrs-open", "MRS requires all banks precharged")
        elif cmd.op == "ZQC":
            if not self.all_precharged():
                self._bad(cmd, "zqc-open", "ZQ calibration requires all banks precharged")
        elif cmd.op == "BST":
            if not self.in_burst:
                self._bad(cmd, "bst-idle", "burst stop while idle")
        elif cmd.op == "RESET":
            pass
        else:
            self._bad(cmd, "opcode", f"unknown opcode {cmd.op}")

    def _check_act(self, cmd: RpcCommand) -> None:
        if not 0 <= cmd.bank < self.p.n_banks:
            self._bad(cmd, "bank", "bank out of range")
            return
        b = self.banks[cmd.bank]
        if b.row is not None:
            self._bad(cmd, "act-open", f"bank {cmd.bank} already open on row {b.row}")
        if cmd.cycle < b.act_ok:
            self._bad(cmd, "tRP/tRC", f"ACT at {cmd.cycle}, bank ready at {b.act_ok}")
        if cmd.cycle < self.last_act + self.p.tRRD_ck:
            self._bad(cmd, "tRRD", f"ACT spacing {cmd.cycle - self.last_act} < tRRD {self.p.tRRD_ck}")
        if not 0 <= cmd.row < self.p.n_rows:
            self._bad(cmd, "row", "row out of range")

    def _check_pre(self, cmd: RpcCommand) -> None:
        if cmd.mask == 0:
            self._bad(cmd, "pre-mask", "PRE with no banks selected")
        for i in range(self.p.n_banks):
            if not (cmd.mask & (1 << i)):
                continue
            b = self.banks[i]
            # PRE of an already-idle bank is a no-op. The init sequence issues
            # PRE ALL while every bank is idle (datasheet section 4).
            if b.row is None:
                continue
            if cmd.cycle < b.pre_ok:
                self._bad(cmd, "tRAS/tWR", f"PRE bank {i} at {cmd.cycle}, legal at {b.pre_ok}")
            if self.in_burst and i == self.burst_bank:
                self._bad(cmd, "pre-burst-bank", "PRE of the bank currently bursting")

    def _check_cas(self, cmd: RpcCommand) -> None:
        if not 0 <= cmd.bank < self.p.n_banks:
            self._bad(cmd, "bank", "bank out of range")
            return
        b = self.banks[cmd.bank]
        if b.row is None:
            self._bad(cmd, "row-closed", f"{cmd.op} to a precharged bank")
            return
        if cmd.cycle < b.act_cycle + self.p.tRCD_ck:
            self._bad(cmd, "tRCD",
                      f"{cmd.op} at {cmd.cycle}, tRCD legal at {b.act_cycle + self.p.tRCD_ck}")
        if cmd.col & 0xF:
            self._bad(cmd, "col-align", "CA[3:0] must be 0 (BL16)")
        n = cmd.bc + 1
        if not 1 <= n <= 64:
            self._bad(cmd, "bc", f"word count {n} outside 1..64")
        if self.zout_open and cmd.op == "RD":
            self._bad(cmd, "zout-open", "read while Zout is open; data bus is disabled")
        start = cmd.cycle + (self.rl if cmd.op == "RD" else self.wl)
        if start < self.data_until:
            self._bad(cmd, "data-bus", f"data starts at {start}, bus free at {self.data_until}")
        if self.in_burst and self.burst_dir and self.burst_dir != cmd.op:
            need = self.p.tWTR_ck if self.burst_dir == "WR" else self.p.tRTW_ck
            if cmd.cycle < self.burst_anchor + need and need:
                self._bad(cmd, "turnaround", f"{self.burst_dir} to {cmd.op} bubble")

    def _check_ref(self, cmd: RpcCommand) -> None:
        if self.in_burst:
            self._bad(cmd, "ref-burst", "REF while bursting; stop the burst first")
        if cmd.mask == 0:
            self._bad(cmd, "ref-mask", "REF with no banks selected")
        if cmd.ref_op not in (0, 1):
            self._bad(cmd, "ref-op", "REFOP1 is reserved")
        for i, bank in enumerate(self.banks):
            if cmd.cycle < bank.act_ok:
                self._bad(cmd, "tRC", f"REF bank {i} before ACT recovery at {bank.act_ok}")
            if bank.row is None and cmd.cycle < bank.pre_cycle + self.p.tRP_ck:
                self._bad(cmd, "tRP", f"REF bank {i} before PRE recovery")
            if bank.row is not None and cmd.cycle < bank.pre_ok:
                self._bad(cmd, "read/write-recovery", f"REF bank {i} before data recovery")

    def _apply(self, cmd: RpcCommand) -> None:
        if cmd.op == "ACT":
            b = self.banks[cmd.bank]
            b.row = cmd.row
            b.act_cycle = cmd.cycle
            b.pre_ok = cmd.cycle + self.p.tRAS_ck
            b.act_ok = cmd.cycle + self.p.tRC_ck
            self.last_act = cmd.cycle
            if not cmd.serial:
                self.last_parallel = cmd.cycle
        elif cmd.op == "PRE":
            for i in range(self.p.n_banks):
                if cmd.mask & (1 << i):
                    b = self.banks[i]
                    b.row = None
                    b.pre_cycle = cmd.cycle
                    b.act_ok = max(b.act_ok, cmd.cycle + self.p.tRP_ck)
            if not cmd.serial:
                self.last_parallel = cmd.cycle
        elif cmd.op in ("RD", "WR"):
            n = cmd.bc + 1
            start = cmd.cycle + (self.rl if cmd.op == "RD" else self.wl)
            end = start + self.p.burst_ck_per_word * n
            self.data_until = end
            self.burst_data_end = end
            b = self.banks[cmd.bank]
            if cmd.op == "WR":
                b.pre_ok = max(b.pre_ok, end + self.p.tWR_ck)
                self._write_burst(cmd, n)
            else:
                b.pre_ok = max(b.pre_ok, end)
                cmd.result = self._read_burst(cmd, n)
            if not cmd.serial:
                self.in_burst = True
                self.burst_anchor = cmd.cycle
                self.last_parallel = cmd.cycle
            self.burst_dir = cmd.op
            self.burst_bank = cmd.bank
        elif cmd.op == "REF":
            # One-shot: precharge all banks, then refresh selected banks.
            n_sel = bin(cmd.mask & 0xF).count("1")
            period = self.p.tREFI_lp_ps if cmd.ref_op else self.p.tREFI_fst_ps
            dur = self.p.n_rows * ck_ceil(period, self.p.tck_ps) * n_sel
            for i in range(self.p.n_banks):
                self.banks[i].row = None
                self.banks[i].pre_cycle = cmd.cycle
                self.banks[i].act_ok = max(self.banks[i].act_ok, cmd.cycle + dur)
            self.busy_until = cmd.cycle + dur
            self.in_burst = False
            self.last_parallel = cmd.cycle
        elif cmd.op == "MRS":
            if cmd.cl:
                self.cl = cmd.cl
            self.zout_open = cmd.zout_open
            self.last_parallel = cmd.cycle
            self.busy_until = max(self.busy_until, cmd.cycle + self.p.tMOD_ck)
        elif cmd.op == "ZQC":
            self.last_parallel = cmd.cycle
            self.busy_until = max(self.busy_until, cmd.cycle + self.p.tZQINIT_ck)
        elif cmd.op == "BST":
            self.in_burst = False
            self.burst_dir = None
            self.burst_bank = None
        elif cmd.op == "RESET":
            self.in_burst = False
            self.initialized = True
            self.zout_open = True
            for b in self.banks:
                b.row = None
                b.act_ok = cmd.cycle + self.p.tRESET_ck
            self.busy_until = cmd.cycle + self.p.tRESET_ck

    def _write_burst(self, cmd: RpcCommand, n_words: int) -> None:
        enable = cmd.enable or bytes([0xFF]) * (n_words * self.p.word_bytes)
        data = cmd.data or bytes(n_words * self.p.word_bytes)
        for w in range(n_words):
            col = (cmd.col + 16 * w) % 1024
            base = flat_addr(cmd.bank, self.banks[cmd.bank].row, col, self.p)
            chunk = data[w * 32:(w + 1) * 32]
            en = enable[w * 32:(w + 1) * 32]
            if len(chunk) < 32:
                chunk = chunk + bytes(32 - len(chunk))
                en = en + bytes(32 - len(en))
            self.mem.write(base, chunk, en)

    def _read_burst(self, cmd: RpcCommand, n_words: int) -> bytes:
        out = bytearray()
        row = self.banks[cmd.bank].row
        for w in range(n_words):
            col = (cmd.col + 16 * w) % 1024
            base = flat_addr(cmd.bank, row, col, self.p)
            out += self.mem.read(base, 32)
        return bytes(out)

    def _bad(self, cmd: RpcCommand, code: str, detail: str) -> None:
        self.violations.append(Violation(cmd.cycle, code, f"{cmd.op}: {detail}"))


class RpcDramFased:
    """Open-page or closed-page scheduler that drives :class:`RpcDramDevice`.

    Open-page mode keeps a row open and uses serial column commands to stream.
    Closed-page mode ACT/CAS/PRE each access, which is what the ETH command
    FSM does (it precharges after every read or write).
    """

    def __init__(self, params: RpcDramParams | None = None, *, page: str = "open",
                 refresh: bool = False):
        if page not in ("open", "closed"):
            raise ValueError("page must be open or closed")
        self.p = params or RpcDramParams()
        self.page = page
        self.refresh = refresh
        self.dev = RpcDramDevice(self.p, assume_initialized=True)
        self.cursor = 0
        self.next_refresh = self.p.retention_ck if refresh else 10**18
        self.refresh_stall = 0
        self.trace: list[str] = []

    def load(self, addr: int, data: bytes) -> None:
        self.dev.mem.write(addr, data)

    def run(self, requests: list[AxiRequest], *, outstanding: int = 1) -> list[Completion]:
        out = []
        for req in requests:
            if outstanding <= 1 and out:
                self.cursor = max(self.cursor, out[-1].done_cycle, req.issue)
            else:
                self.cursor = max(self.cursor, req.issue, self.dev.busy_until)
            self._maybe_refresh()
            out.append(self._service(req))
        self._end_burst()
        if self.dev.violations:
            raise RuntimeError("scheduler produced an illegal command: "
                               + "; ".join(map(str, self.dev.violations)))
        return out

    def _maybe_refresh(self) -> None:
        if self.cursor < self.next_refresh:
            return
        self._end_burst()
        self._precharge_mask(0xF, self.cursor)
        ref_ready = max(
            max(b.act_ok for b in self.dev.banks),
            max(b.pre_cycle + self.p.tRP_ck for b in self.dev.banks),
            max((b.pre_ok for b in self.dev.banks if b.row is not None), default=0),
            self.dev.data_until,
            self.cursor,
            self.dev.cycle,
        )
        cycle = self._earliest_parallel(ref_ready)
        before = self.dev.busy_until
        self.dev.issue(RpcCommand("REF", cycle, mask=0xF, ref_op=0))
        self.refresh_stall += self.dev.busy_until - before
        self.cursor = self.dev.busy_until
        self.next_refresh = self.cursor + self.p.retention_ck

    def _service(self, req: AxiRequest) -> Completion:
        if req.length == 0:
            return Completion(req.xid, req.is_write, req.addr, b"", self.cursor,
                              self.cursor, self.cursor)
        accept = self.cursor
        offset = 0
        first = None
        data_out = bytearray()
        hit_any = False
        bank0 = row0 = None
        while offset < req.length:
            addr = req.addr + offset
            bank, row, col, _off = decode_addr(addr & ~31, self.p)
            if bank0 is None:
                bank0, row0 = bank, row
            page_off = addr & (self.p.page_bytes - 1)
            room = self.p.page_bytes - page_off
            n = min(req.length - offset, room)
            # Cover n bytes starting at addr, which may be unaligned.
            hit = self._open_row(bank, row)
            hit_any = hit_any or hit
            piece = self._transfer(req, offset, n, bank, row)
            if not req.is_write:
                data_out += piece
            if first is None:
                first = self.dev.commands[-1].cycle + self.dev.rl
            offset += n
            self.cursor = self.dev.commands[-1].cycle
        if self.page == "closed":
            self._end_burst()
            self._precharge_mask(1 << bank0, self.cursor)
            self.cursor = max(self.cursor, self.dev.cycle)
        done = self.dev.data_until
        self.trace.append(
            f"RPCREQ,{accept},{int(req.is_write)},{req.addr:x},{req.xid},{req.length},"
            f"{bank0},{row0:x},{int(hit_any)}"
        )
        return Completion(
            xid=req.xid, is_write=req.is_write, addr=req.addr,
            data=bytes(data_out) if not req.is_write else req.data,
            accept_cycle=accept, first_data_cycle=first if first is not None else accept,
            done_cycle=done, row_hit=hit_any, bank=bank0, row=row0,
            cmds=list(self.dev.commands),
        )

    def _open_row(self, bank: int, row: int) -> bool:
        """Make ``row`` open. Returns True if it was already open (row hit)."""
        b = self.dev.banks[bank]
        if b.row == row and not self._row_will_close(bank):
            return True
        if b.row is not None:
            if self.dev.in_burst and self.dev.burst_bank == bank:
                self._end_burst()
            self._precharge_mask(1 << bank, self.cursor)
        self._activate(bank, row)
        return False

    def _row_will_close(self, bank: int) -> bool:
        return False

    def _activate(self, bank: int, row: int) -> None:
        b = self.dev.banks[bank]
        ready = max(self.cursor, b.act_ok, self.dev.last_act + self.p.tRRD_ck, self.dev.busy_until)
        if self.dev.in_burst and self.cursor < self.dev.burst_data_end:
            slot = self._align_serial(ready)
            # A serial ACT that would land after the burst just ends is issued
            # as a parallel ACT instead.
            if slot + self.p.tRCD_ck < self.dev.burst_data_end:
                self.dev.issue(RpcCommand("ACT", slot, bank=bank, row=row, serial=True))
                self.cursor = slot
                return
            self._end_burst()
        self._end_burst()
        slot = self._earliest_parallel(ready)
        self.dev.issue(RpcCommand("ACT", slot, bank=bank, row=row, serial=False))
        self.cursor = slot

    def _transfer(self, req: AxiRequest, offset: int, n: int, bank: int, row: int) -> bytes:
        addr = req.addr + offset
        # Walk 32 B words covering [addr, addr+n).
        first_word = addr & ~31
        last = addr + n
        cursor_addr = first_word
        collected = bytearray()
        while cursor_addr < last:
            bank_i, row_i, col, _ = decode_addr(cursor_addr, self.p)
            if (bank_i, row_i) != (bank, row):
                break
            # How many contiguous words stay on this row and inside ``n``?
            words = 0
            a = cursor_addr
            while a < last and words < 64:
                bi, ri, _, _ = decode_addr(a, self.p)
                if (bi, ri) != (bank, row):
                    break
                words += 1
                a += 32
            self._cas(req, offset + (cursor_addr - (req.addr + offset)), words, bank, row, col,
                      cursor_addr, addr, n)
            # Pull the host-visible slice out of the last command.
            if not req.is_write:
                blob = self.dev.commands[-1].result
                for w in range(words):
                    word_addr = cursor_addr + 32 * w
                    lo = max(word_addr, addr)
                    hi = min(word_addr + 32, addr + n)
                    collected += blob[w * 32 + (lo - word_addr): w * 32 + (hi - word_addr)]
            cursor_addr += 32 * words
        return bytes(collected)

    def _cas(self, req, host_off, words, bank, row, col, word_addr, span_addr, span_n) -> None:
        op = "WR" if req.is_write else "RD"
        # Build the 32B*words image and mask relative to the host span.
        raw = bytearray(words * 32)
        en = bytearray(words * 32)
        for w in range(words):
            base = word_addr + 32 * w
            for b in range(32):
                abs_a = base + b
                if span_addr <= abs_a < span_addr + span_n:
                    rel = abs_a - req.addr
                    if req.is_write:
                        raw[w * 32 + b] = req.data[rel]
                        en[w * 32 + b] = 1 if req.strb[rel] else 0
                    else:
                        en[w * 32 + b] = 1
        bc = words - 1
        bstate = self.dev.banks[bank]
        ready = max(self.cursor, bstate.act_cycle + self.p.tRCD_ck, self.dev.busy_until)
        use_serial = (
            self.dev.in_burst
            and self.dev.burst_dir == op
            and self.cursor < self.dev.burst_data_end
        )
        if use_serial:
            slot = self._align_serial(max(ready, self.dev.data_until - (self.dev.rl if op == "RD" else self.dev.wl)))
            if slot >= self.dev.burst_data_end:
                use_serial = False
            else:
                self.dev.issue(RpcCommand(op, slot, bank=bank, row=row, col=col, bc=bc,
                                          serial=True, data=bytes(raw), enable=bytes(en)))
                self.cursor = slot
                return
        if self.dev.in_burst:
            self._end_burst()
        slot = max(ready, self.dev.data_until - self.dev.rl)
        # data bus: start >= data_until
        lat = self.dev.rl
        if slot + lat < self.dev.data_until:
            slot = self.dev.data_until - lat
        slot = self._earliest_parallel(slot)
        self.dev.issue(RpcCommand(op, slot, bank=bank, row=row, col=col, bc=bc,
                                  serial=False, data=bytes(raw), enable=bytes(en)))
        self.cursor = slot

    def _precharge_mask(self, mask: int, now: int) -> None:
        if mask == 0:
            return
        live = 0
        ready = now
        for i in range(self.p.n_banks):
            if mask & (1 << i) and self.dev.banks[i].row is not None:
                live |= 1 << i
                ready = max(ready, self.dev.banks[i].pre_ok)
        if not live:
            return
        if self.dev.in_burst and (live & (1 << (self.dev.burst_bank or 0))):
            self._end_burst()
        slot = self._earliest_parallel(max(ready, self.dev.busy_until, self.cursor))
        self.dev.issue(RpcCommand("PRE", slot, mask=live, serial=False))
        self.cursor = slot

    def _end_burst(self) -> None:
        if not self.dev.in_burst:
            return
        slot = self._align_serial(max(self.cursor, self.dev.burst_anchor + 8))
        if slot >= self.dev.burst_data_end:
            self.dev._catch_up(self.dev.burst_data_end)
            self.cursor = max(self.cursor, self.dev.burst_data_end)
            return
        self.dev.issue(RpcCommand("BST", slot, serial=True))
        self.cursor = max(self.cursor, slot)

    def _earliest_parallel(self, target: int = 0) -> int:
        if self.dev.last_parallel is None:
            return target
        target = max(target, self.dev.last_parallel + self.dev.tppd())
        if not self.dev.all_precharged():
            gap = self.p.tPPD_act_ck
            target += (-(target - self.dev.last_parallel)) % gap
        return target

    def _align_serial(self, cycle: int) -> int:
        anchor = self.dev.burst_anchor
        if cycle <= anchor:
            return anchor + 8
        delta = cycle - anchor
        rem = delta % 8
        if rem:
            cycle += 8 - rem
        if cycle == anchor:
            cycle += 8
        return cycle


def theoretical_bandwidth_MBps(params: RpcDramParams | None = None) -> float:
    """Peak data bandwidth: 4 bytes per CK (x16 DDR)."""
    p = params or RpcDramParams()
    return (4.0 / p.tck_ps) * 1e6
