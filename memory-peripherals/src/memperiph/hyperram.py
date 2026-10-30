"""HyperRAM device and FASED-style transaction model.

The device speaks the host-visible HyperBus transaction: a 48-bit
command/address, an initial latency, optional refresh-collision latency, and
a DDR byte stream. It does not model DQ/RWDS analog timing.

The part targeted by the defaults is Infineon S80KS2562 (256 Mbit, 1.8 V).
Numeric defaults are checked against S80KS2562 Rev. *C (002-31337).
Every value is listed in ``catalog()`` with its source. Internal refresh
phase is not specified by the datasheet; the collision schedule below is
a deterministic performance assumption, not a pin-level specification.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .util import AxiRequest, Completion, SparseMem, Violation, ck_ceil


# CR0[7:4] initial-latency codes. Clocks of CK, not doubled.
# HyperRAM 2.0 configuration register 0.
_LATENCY_CODE = {0x0: 5, 0x1: 6, 0x2: 7, 0xE: 3, 0xF: 4}

# CR0[1:0] wrapped burst length in bytes.
_WRAP_CODE = {0b00: 128, 0b01: 64, 0b10: 16, 0b11: 32}

# CR1[4:2] partial-array refresh window as (start_num, end_num) over 8 slices.
_PAR_SLICES = {
    0b000: (0, 8),  # full array
    0b001: (0, 4),  # bottom half
    0b010: (0, 2),  # bottom quarter
    0b011: (0, 1),  # bottom eighth
    0b100: (0, 0),  # none
    0b101: (4, 8),  # top half
    0b110: (6, 8),  # top quarter
    0b111: (7, 8),  # top eighth
}

REG_ID0 = 0x0000
REG_ID1 = 0x0001
REG_CR0 = 0x0800
REG_CR1 = 0x0801


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
class HyperRAMParams:
    """S80KS2562-class HyperRAM, 200 MHz 1.8 V column unless overridden."""

    size_bytes: int = 32 * 1024 * 1024
    row_bytes: int = 1024
    tck_ps: int = 5_000
    tCSHI_ps: int = 6_000
    tRWR_ps: int = 35_000
    tRP_ps: int = 200_000
    tRH_ps: int = 200_000
    tCSM_ps: int = 4_000_000
    tRFH_ps: int = 35_000
    tACC_ps: int = 35_000
    ca_ck: int = 3
    # 200 MHz 1.8 V power-on CR0: latency code 2 (7 CK), fixed latency, 32 B wrap.
    cr0_reset: int = 0x8F2F
    # {14'h3FF0, DRI=01}. DRI=01 selects the 4 us industrial tCSM column.
    cr1_reset: int = 0xFFC1
    # Identification Register 0. Infineon S80KS2562 datasheet section 6.2.1.
    id0_reset: int = 0x0E86
    id1_reset: int = 0x0001
    ingress_depth: int = 16

    def __post_init__(self) -> None:
        if self.size_bytes % self.row_bytes:
            raise ValueError("size must be a multiple of the row size")
        if self.tck_ps <= 0:
            raise ValueError("tCK must be positive")

    @property
    def n_rows(self) -> int:
        return self.size_bytes // self.row_bytes

    @property
    def tCSHI_ck(self) -> int:
        return max(1, ck_ceil(self.tCSHI_ps, self.tck_ps))

    @property
    def tRWR_ck(self) -> int:
        return ck_ceil(self.tRWR_ps, self.tck_ps)

    @property
    def tRP_ck(self) -> int:
        return ck_ceil(self.tRP_ps, self.tck_ps)

    @property
    def tRH_ck(self) -> int:
        return ck_ceil(self.tRH_ps, self.tck_ps)

    @property
    def tCSM_ck(self) -> int:
        return ck_ceil(self.tCSM_ps, self.tck_ps)

    @property
    def tRFH_ck(self) -> int:
        return max(1, ck_ceil(self.tRFH_ps, self.tck_ps))

    def catalog(self) -> list[Param]:
        src = "Infineon HyperRAM 2.0 / S80KS2562 family (1.8 V, 200 MHz column)"
        return [
            Param("size_bytes", "33554432", "B", src, "density 256 Mbit", "specified",
                  "S80KS2562 is 256 Mbit = 32 MiB."),
            Param("row_bytes", "1024", "B", "S80KS2562 Rev. *C",
                  "Table 5 and section 6.2.1", "specified",
                  "512 words per row, 2 bytes per word, 32768 rows."),
            Param("tck_ps", "5000", "ps", src, "tCK max frequency 200 MHz", "specified",
                  "S80KS2562GABHB020 is the 200 MHz 1.8 V grade."),
            Param("tCSHI_ps", "6000", "ps", src, "tCSHI", "specified",
                  "Minimum CS# high between transactions. 6.0 ns at 200 MHz."),
            Param("tRWR_ps", "35000", "ps", src, "tRWR", "specified",
                  "Read-to-write recovery, CS# high. 35 ns at the 200 MHz 1.8 V column."),
            Param("tRP_ps", "200000", "ps", src, "tRP", "specified",
                  "RESET# pulse width. Not a DRAM precharge. 200 ns."),
            Param("tRH_ps", "200000", "ps", src, "tRH", "specified",
                  "RESET# high to first CS#. 200 ns at this speed grade."),
            Param("tCSM_ps", "4000000", "ps", src, "tCSM", "specified",
                  "Maximum CS# low. 4 us industrial. The device cannot refresh while selected."),
            Param("tRFH_ps", "35000", "ps", src, "tRFH", "specified",
                  "Distributed-refresh time for one row. Equals tACC at 200 MHz (35 ns)."),
            Param("tACC_ps", "35000", "ps", src, "tACC", "specified",
                  "Initial access time. 7 CK * 5 ns = 35 ns at the default latency code."),
            Param("refresh_phase", "reset origin", "assumption", src,
                  "section 6.3.2", "approximation",
                  "The datasheet specifies the maximum distributed refresh interval (tCSM), not the internal phase. This model chooses reset as phase zero; a pin-level test should inject collisions at either latency."),
            Param("ca_ck", "3", "CK", "HyperBus specification", "CA phase", "specified",
                  "48-bit command/address, DDR, 3 CK."),
            Param("cr0_reset", "0x8F2F", "code", src, "CR0 power-on", "specified",
                  "Latency code 0010 = 7 CK, fixed latency, legacy 32-byte wrap. Same encoding as the 1.8 V 200 MHz HyperRAM 2.0 default."),
            Param("cr1_reset", "0xFFC1", "code", src, "CR1 power-on", "specified",
                  "Partial refresh = full array, DRI selects 4 us tCSM."),
            Param("id0_reset", "0x0E86", "code", "Infineon S80KS2562 datasheet", "section 6.2.1", "specified",
                  "Identification Register 0 power-on value. Read-only."),
            Param("tCSM_hot_ps", "1000000", "ps", src, "tCSM", "specified",
                  "tCSM shrinks to 1 us for Tc above 85 C. The default model uses the 4 us, <=85 C column. Set tCSM_ps=1000000 for the hot column."),
            Param("ca_map", "CA[47]=R/W#, CA[46]=AS, CA[45]=burst, CA[44:16]=row/upper col, CA[2:0]=lower col",
                  "bits", "HyperBus specification", "48-bit CA", "specified",
                  "AS=0 memory, AS=1 register. Burst type 0 = wrapped, 1 = linear."),
            Param("rwds_mask", "RWDS high masks the byte on a write", "level", "HyperBus specification",
                  "RWDS", "specified", "Read data uses RWDS as the strobe. Write data uses RWDS as an active-high mask."),
            Param("variable_latency", "2x initial latency when a refresh collides", "CK", src,
                  "initial latency / RWDS during CA", "specified",
                  "Fixed-latency mode (CR0[3]=1) always waits 2x and drives RWDS high during CA."),
        ]


@dataclass
class HyperTxn:
    is_write: bool
    space: str
    addr: int
    nbytes: int
    start: int
    latency_ck: int
    rwds_high: bool
    first_data: int
    done: int
    data: bytes
    cs_low_ck: int
    violated_tcsm: bool


class HyperRAMDevice:
    """One HyperRAM chip. Time is an integer count of CK cycles."""

    def __init__(self, params: HyperRAMParams | None = None, *, strict: bool = True):
        self.p = params or HyperRAMParams()
        self.strict = strict
        self.mem = SparseMem(self.p.size_bytes)
        self.violations: list[Violation] = []
        self.history: list[HyperTxn] = []
        self.cycle = 0
        self.cr0 = self.p.cr0_reset
        self.cr1 = self.p.cr1_reset
        self.id0 = self.p.id0_reset
        self.id1 = self.p.id1_reset
        self.dpd = False
        self.reset_done = False
        self._origin = 0
        self._ref_completed = 0
        self._cs_rise = 0
        self._last_dir: str | None = None
        self.extra_latency_count = 0
        # Cycle 0 is the first legal CS#. power_on_reset() is the explicit
        # sequence that spends tRP + tRH before that point.
        self._release()

    # ------------------------------------------------------------------
    # reset
    # ------------------------------------------------------------------
    def power_on_reset(self) -> int:
        """Assert RESET# for tRP, then wait tRH. Returns the first legal cycle."""
        self.cycle = 0
        self.reset_done = False
        self.dpd = False
        done = self.p.tRP_ck + self.p.tRH_ck
        self.cycle = done
        self._release()
        return done

    def wait(self, n_ck: int) -> None:
        if n_ck < 0:
            raise ValueError("cannot wait a negative number of cycles")
        self.cycle += n_ck

    def reset_pulse(self, *, at: int | None = None) -> int:
        """Hardware reset starting at ``at`` (default: now)."""
        if at is None:
            at = self.cycle
        if at < self.cycle:
            self._bad(at, "reset-backwards", "reset time is earlier than the device clock")
        self.cycle = at + self.p.tRP_ck + self.p.tRH_ck
        self._release()
        return self.cycle

    def _release(self) -> None:
        self.cr0 = self.p.cr0_reset
        self.cr1 = self.p.cr1_reset
        self.id0 = self.p.id0_reset
        self.id1 = self.p.id1_reset
        self.dpd = False
        self.reset_done = True
        self._origin = self.cycle
        self._ref_completed = 0
        self._cs_rise = self.cycle
        self._last_dir = None

    # ------------------------------------------------------------------
    # CR0 / CR1 view
    # ------------------------------------------------------------------
    def latency_code_ck(self) -> int:
        code = (self.cr0 >> 4) & 0xF
        if code not in _LATENCY_CODE:
            self._bad(self.cycle, "cr0-latency", f"reserved CR0 latency code {code:#x}")
            return 7
        return _LATENCY_CODE[code]

    @property
    def fixed_latency(self) -> bool:
        return bool(self.cr0 & 0x8)

    @property
    def hybrid(self) -> bool:
        # CR0[2] = 0 selects hybrid burst. CR0[2] = 1 is legacy wrapped/linear.
        return (self.cr0 & 0x4) == 0

    def wrap_bytes(self) -> int:
        return _WRAP_CODE[self.cr0 & 0x3]

    def covered_rows(self) -> int:
        sel = (self.cr1 >> 2) & 0x7
        a, b = _PAR_SLICES[sel]
        return ((b - a) * self.p.n_rows) // 8

    def rows_required(self, cycle: int) -> int:
        n = self.covered_rows()
        if n == 0:
            return 0
        elapsed = max(0, cycle - self._origin)
        # Section 6.3.2 sets the maximum adjacent refresh interval equal to
        # tCSM (4 us or 1 us). The internal phase is not published; reset is
        # the deterministic phase origin for this performance model.
        return elapsed // self.p.tCSM_ck

    # ------------------------------------------------------------------
    # host transactions
    # ------------------------------------------------------------------
    def read(self, addr: int, n: int, *, space: str = "mem", linear: bool = True,
             at: int | None = None, obey_timing: bool = True) -> HyperTxn:
        return self.transaction(False, addr, n, space=space, linear=linear, at=at,
                                obey_timing=obey_timing)

    def write(self, addr: int, data: bytes, byte_enable: bytes | None = None, *,
              space: str = "mem", linear: bool = True, at: int | None = None,
              obey_timing: bool = True) -> HyperTxn:
        return self.transaction(True, addr, len(data), data=data, byte_enable=byte_enable,
                                space=space, linear=linear, at=at, obey_timing=obey_timing)

    def transaction(self, is_write: bool, addr: int, n: int, *, data: bytes | None = None,
                    byte_enable: bytes | None = None, space: str = "mem", linear: bool = True,
                    at: int | None = None, obey_timing: bool = True) -> HyperTxn:
        if n < 0 or n % 2:
            raise ValueError("HyperBus transfers an even number of bytes (16-bit words)")
        if space not in ("mem", "reg"):
            raise ValueError("space must be mem or reg")
        if is_write and (data is None or len(data) != n):
            raise ValueError("write data length mismatch")
        if at is not None:
            if at < self.cycle:
                self._bad(at, "time-reversal", "transaction scheduled in the past")
            else:
                self.cycle = at

        direction = "W" if is_write else "R"
        gap = self._required_gap(direction)
        earliest = self._cs_rise + gap
        if self.cycle < earliest:
            if obey_timing:
                self.cycle = earliest
            else:
                self._bad(self.cycle, "cs-high",
                          f"{direction} gap {self.cycle - self._cs_rise} CK < {gap} CK")

        if not self.reset_done:
            self._bad(self.cycle, "reset", "transaction before reset completed")
        if self.dpd and not (space == "reg" and not is_write):
            self._bad(self.cycle, "dpd", "transaction while in deep power down")

        start = self.cycle
        gap_ck = start - self._cs_rise
        self._service_gap(start, gap_ck)
        due = self.rows_required(start) - self._ref_completed
        collision = due >= 1
        doubled = self.fixed_latency or collision
        # Section 6.3: register writes transfer one word immediately after
        # the 3-CK CA phase. Register reads retain normal read latency.
        lat = 0 if (space == "reg" and is_write) else self.latency_code_ck() * (2 if doubled else 1)
        if doubled and collision:
            self._ref_completed += 1
            self.extra_latency_count += 1

        # Capture latency before a register write can change CR0.
        addrs = self._addresses(addr, n, space, linear)
        if space == "mem":
            for a in addrs:
                if not 0 <= a < self.p.size_bytes:
                    self._bad(start, "addr", f"byte {a} outside device")

        cs_low = self.p.ca_ck + lat + n // 2
        violated_tcsm = cs_low > self.p.tCSM_ck
        if violated_tcsm:
            self._bad(start, "tCSM",
                      f"CS# low for {cs_low} CK, tCSM is {self.p.tCSM_ck} CK")

        first = start + self.p.ca_ck + lat
        if is_write:
            assert data is not None
            enable = byte_enable if byte_enable is not None else bytes([0xFF]) * n
            if len(enable) != n:
                raise ValueError("byte enable length mismatch")
            self._apply_write(space, addrs, data, enable)
            out = data
        else:
            out = self._gather(space, addrs)

        done = start + cs_low
        self.cycle = done
        self._cs_rise = done
        self._last_dir = direction
        txn = HyperTxn(
            is_write=is_write, space=space, addr=addr, nbytes=n, start=start,
            latency_ck=lat, rwds_high=doubled, first_data=first, done=done,
            data=out, cs_low_ck=cs_low, violated_tcsm=violated_tcsm,
        )
        self.history.append(txn)
        return txn

    def max_payload_bytes(self, latency_ck: int) -> int:
        """Largest even payload whose single CS# assertion respects tCSM."""
        room = self.p.tCSM_ck - self.p.ca_ck - latency_ck
        if room < 1:
            return 0
        return room * 2

    # ------------------------------------------------------------------
    # refresh accounting
    # ------------------------------------------------------------------
    def _service_gap(self, cycle: int, gap_ck: int) -> None:
        can = max(0, gap_ck) // self.p.tRFH_ck
        due = self.rows_required(cycle) - self._ref_completed
        self._ref_completed += min(can, max(0, due))

    def _required_gap(self, direction: str) -> int:
        if self._last_dir == "R" and direction == "W":
            return max(self.p.tCSHI_ck, self.p.tRWR_ck)
        if self._last_dir is None:
            return 0
        return self.p.tCSHI_ck

    def _addresses(self, start: int, n: int, space: str, linear: bool) -> list[int]:
        if start % 2:
            self._bad(self.cycle, "align", "HyperBus address must be 16-bit aligned")
            start -= start % 2
        if space == "reg":
            return [start + i for i in range(n)]
        # CR0[2] controls the wrapped sequence only when CA[45] is zero.
        if self.hybrid and not linear:
            return self._wrapped(start, n, self.wrap_bytes(), switch_linear=True)
        if linear:
            # Section 4.2/4.3: a linear burst wraps at the end of the array.
            return [(start + i) % self.p.size_bytes for i in range(n)]
        return self._wrapped(start, n, self.wrap_bytes(), switch_linear=False)

    def _wrapped(self, start: int, n: int, wrap: int, *, switch_linear: bool) -> list[int]:
        base = start & ~(wrap - 1)
        out = []
        for i in range(n):
            if switch_linear and i >= wrap:
                # After one wrapped burst, continue linearly past the group.
                out.append(base + wrap + (i - wrap))
            else:
                out.append(base + ((start + i - base) % wrap))
        return out

    def _apply_write(self, space: str, addrs: list[int], data: bytes, enable: bytes) -> None:
        if space == "reg":
            self._write_reg(addrs, data, enable)
            return
        for a, val, en in zip(addrs, data, enable):
            if 0 <= a < self.p.size_bytes and en:
                self.mem.write(a, bytes([val]), bytes([0xFF]))

    def _gather(self, space: str, addrs: list[int]) -> bytes:
        if space == "reg":
            return self._read_reg(addrs)
        out = bytearray(len(addrs))
        for i, a in enumerate(addrs):
            if 0 <= a < self.p.size_bytes:
                out[i] = self.mem.read(a, 1)[0]
        return bytes(out)

    def _read_reg(self, addrs: list[int]) -> bytes:
        # Register reads return the 16-bit register, even byte first, and
        # repeat that same register if the host holds CS# (section 6.3).
        out = bytearray()
        if not addrs:
            return bytes(out)
        reg = self._reg_value((addrs[0] // 2) & 0xFFFF)
        for i in range(len(addrs)):
            out.append((reg >> 8) & 0xFF if (i % 2 == 0) else reg & 0xFF)
        return bytes(out)

    def _write_reg(self, addrs: list[int], data: bytes, enable: bytes) -> None:
        # Section 6.3: one unmasked 16-bit word, with no initial latency.
        if not addrs:
            return
        if len(addrs) != 2:
            self._bad(self.cycle, "reg-length", "register write must be one 16-bit word")
            return
        if any(not en for en in enable):
            self._bad(self.cycle, "reg-mask", "RWDS is not a register-write byte mask")
            return
        word = addrs[0] // 2
        if word in (REG_ID0, REG_ID1):
            self._bad(self.cycle, "id-ro", f"write to read-only ID register {word:#x} ignored")
            return
        cur = self._reg_value(word)
        hi = (cur >> 8) & 0xFF
        lo = cur & 0xFF
        for a, val, en in zip(addrs, data, enable):
            if not en:
                continue
            if a // 2 != word:
                self._bad(self.cycle, "reg-span", "register write crossed into another word")
                break
            if a % 2 == 0:
                hi = val
            else:
                lo = val
        new = (hi << 8) | lo
        if word == REG_CR0:
            if (new & 0x0F00) != 0x0F00:
                self._bad(self.cycle, "cr0-reserved", "CR0[11:8] must keep their reset value")
                return
            if ((new >> 4) & 0xF) not in _LATENCY_CODE:
                self._bad(self.cycle, "cr0-latency", "reserved CR0 latency code")
                return
            self.cr0 = new
            self.dpd = (new & 0x8000) == 0
        elif word == REG_CR1:
            if (new & 0xFF80) != 0xFF80:
                self._bad(self.cycle, "cr1-reserved", "CR1 reserved bits must keep their reset values")
                return
            if (new & 0x3) != (self.cr1 & 0x3):
                self._bad(self.cycle, "cr1-readonly", "CR1[1:0] is read only")
            self.cr1 = (new & ~0x3) | (self.cr1 & 0x3)
        else:
            self._bad(self.cycle, "reg-addr", f"write to undefined register {word:#x}")

    def _reg_value(self, word: int) -> int:
        return {
            REG_ID0: self.id0,
            REG_ID1: self.id1,
            REG_CR0: self.cr0,
            REG_CR1: self.cr1,
        }.get(word, 0)

    def _bad(self, cycle: int, code: str, detail: str) -> None:
        self.violations.append(Violation(cycle, code, detail))
        if self.strict and code in ("time-reversal",):
            raise RuntimeError(str(self.violations[-1]))


class HyperRAMFased:
    """AXI transaction timing model on top of :class:`HyperRAMDevice`.

    One device bus, in-order completions. Requests queue in an ingress FIFO.
    Bursts that would hold CS# longer than tCSM are split into legal
    transactions. This is the SoC-level performance model: it is not a
    pin-accurate controller.
    """

    def __init__(self, params: HyperRAMParams | None = None):
        self.p = params or HyperRAMParams()
        self.dev = HyperRAMDevice(self.p, strict=False)
        self.trace: list[str] = []

    def load(self, addr: int, data: bytes) -> None:
        self.dev.mem.write(addr, data)

    def run(self, requests: list[AxiRequest], *, outstanding: int = 1) -> list[Completion]:
        if outstanding < 1:
            raise ValueError("outstanding must be >= 1")
        done: list[Completion] = []
        pending: list[tuple[AxiRequest, int]] = []
        idx = 0
        # Service in order. ``outstanding`` limits how early a later request
        # may be accepted relative to older unfinished ones: acceptance is
        # still in order because the device has a single CS#.
        while idx < len(requests) or pending:
            while idx < len(requests) and len(pending) < outstanding:
                req = requests[idx]
                accept = max(req.issue, self.dev.cycle if not pending else pending[-1][1] + 1)
                if pending:
                    accept = max(accept, pending[0][1])  # cannot pass the head
                pending.append((req, accept))
                idx += 1
            if not pending:
                break
            req, accept = pending.pop(0)
            comp = self._service(req, accept)
            done.append(comp)
            # Later accepts cannot precede this completion's acceptance.
            pending = [(r, max(a, comp.accept_cycle + 1)) for r, a in pending]
        return done

    def _service(self, req: AxiRequest, accept: int) -> Completion:
        self.dev.cycle = max(self.dev.cycle, accept)
        offset = 0
        first_data = None
        last_done = accept
        extra = False
        stored = bytearray()
        while offset < req.length or req.length == 0:
            # Peek the latency the next CS# would use by asking the device
            # after it has waited out the legal gap. A zero-length request
            # still performs no transfer.
            if req.length == 0:
                break
            lat_now = self._peek_latency("W" if req.is_write else "R")
            room = self.dev.max_payload_bytes(lat_now)
            if room < 2:
                # Pathological programmed latency. Force a 2-byte chunk and
                # let the device flag tCSM.
                room = 2
            n = min(room, req.length - offset)
            if n % 2:
                n -= 1
            if n <= 0:
                n = min(2, req.length - offset)
            addr = req.addr + offset
            if req.is_write:
                txn = self.dev.write(addr, req.data[offset:offset + n],
                                     req.strb[offset:offset + n], linear=True)
            else:
                txn = self.dev.read(addr, n, linear=True)
                stored += txn.data
            if first_data is None:
                first_data = txn.first_data
            last_done = txn.done
            extra = extra or txn.rwds_high
            row = addr // self.p.row_bytes
            self.trace.append(
                f"HYPERREQ,{txn.start},{int(req.is_write)},{addr:x},{req.xid},"
                f"{n},{txn.latency_ck},{int(txn.rwds_high)},{row:x}"
            )
            offset += n
            if offset >= req.length:
                break
        if first_data is None:
            first_data = accept
        return Completion(
            xid=req.xid, is_write=req.is_write, addr=req.addr,
            data=bytes(stored) if not req.is_write else req.data,
            accept_cycle=accept, first_data_cycle=first_data, done_cycle=last_done,
            extra_latency=extra, row=req.addr // self.p.row_bytes,
        )

    def _peek_latency(self, direction: str) -> int:
        """Latency of the next chip-select, without mutating the device."""
        gap_need = self.dev._required_gap(direction)
        earliest = self.dev._cs_rise + gap_need
        start = max(self.dev.cycle, earliest)
        base = self.dev.latency_code_ck()
        if self.dev.fixed_latency:
            return base * 2
        gap = start - self.dev._cs_rise
        completed = self.dev._ref_completed
        can = max(0, gap) // self.dev.p.tRFH_ck
        due = self.dev.rows_required(start) - completed
        completed += min(can, max(0, due))
        if self.dev.rows_required(start) - completed >= 1:
            return base * 2
        return base


def theoretical_bandwidth_MBps(params: HyperRAMParams | None = None) -> float:
    """Peak data-bus bandwidth: 2 bytes per CK. Not a sustained-workload number."""
    p = params or HyperRAMParams()
    return (2.0 / p.tck_ps) * 1e6  # bytes/ps * 1e6 = MB/s
