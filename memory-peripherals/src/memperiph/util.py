"""Shared helpers: sparse memory, timing conversion, violations, AXI requests."""

from __future__ import annotations

from dataclasses import dataclass, field


def ck_ceil(time_ps: int, tck_ps: int) -> int:
    """Convert a picosecond minimum into controller clocks, rounding up."""
    if time_ps <= 0:
        return 0
    return (time_ps + tck_ps - 1) // tck_ps


class SparseMem:
    """Byte-addressable memory that does not allocate the full device."""

    def __init__(self, size: int):
        if size <= 0:
            raise ValueError("memory size must be positive")
        self.size = size
        self._data: dict[int, int] = {}

    def contains(self, addr: int, n: int) -> bool:
        return n >= 0 and addr >= 0 and addr + n <= self.size

    def read(self, addr: int, n: int) -> bytes:
        if not self.contains(addr, n):
            raise IndexError(f"read [{addr}, {addr + n}) outside [0, {self.size})")
        return bytes(self._data.get(addr + i, 0) for i in range(n))

    def write(self, addr: int, data: bytes, enable: bytes | None = None) -> None:
        if not self.contains(addr, len(data)):
            raise IndexError(f"write [{addr}, {addr + len(data)}) outside [0, {self.size})")
        if enable is None:
            enable = bytes([0xFF]) * len(data)
        if len(enable) != len(data):
            raise ValueError("byte enable length must match data")
        for i, (val, en) in enumerate(zip(data, enable)):
            if en:
                self._data[addr + i] = val


@dataclass
class Violation:
    cycle: int
    code: str
    detail: str

    def __str__(self) -> str:
        return f"@{self.cycle} {self.code}: {self.detail}"


@dataclass
class AxiRequest:
    """One AXI INCR burst. Functional data travels with the request.

    ``issue`` is the cycle the target presents the request. The model may
    accept it later if the ingress queue or the device is busy.
    """

    is_write: bool
    addr: int
    length: int
    issue: int = 0
    xid: int = 0
    data: bytes = b""
    strb: bytes = b""

    def __post_init__(self) -> None:
        if self.length < 0:
            raise ValueError("negative length")
        if self.is_write:
            if len(self.data) != self.length:
                raise ValueError("write data length mismatch")
            if not self.strb:
                self.strb = bytes([0xFF]) * self.length
            elif len(self.strb) != self.length:
                raise ValueError("strobe length mismatch")


@dataclass
class Completion:
    xid: int
    is_write: bool
    addr: int
    data: bytes
    accept_cycle: int
    first_data_cycle: int
    done_cycle: int
    extra_latency: bool = False
    row_hit: bool | None = None
    bank: int | None = None
    row: int | None = None
    cmds: list = field(default_factory=list)

    @property
    def latency(self) -> int:
        """Cycles from acceptance to first data (reads) or write completion."""
        if self.is_write:
            return self.done_cycle - self.accept_cycle
        return self.first_data_cycle - self.accept_cycle
