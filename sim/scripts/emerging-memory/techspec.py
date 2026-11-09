"""Cycle-accurate reference for the FASED technology-spec memory.

This models the timing-model boundary in TechSpecMemory.scala, not the later
FASED egress unit and not host DRAM. Outstanding entries decrement when the
timing model presents a response and the sink takes it. In the Chisel model,
TimingModel.pendingReads decrements on the target AXI last beat, which is
later by the egress path and the functional backing memory. Do not treat a
Python queue-full cycle as a measured AXI-port cycle until a metasim says so.

The programmed latency uses the same release formula as LatencyPipe:

    release = start + latency - 1

with egressUnitDelay = 1. Under an ideal host return, that 1 cycle is the
egress unit, so the programmed latency is the intended target-visible delay.
This reference checks the release cycle, not that ideal-host claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field


EGRESS_UNIT_DELAY = 1


def transfer_bytes(length: int, size: int) -> int:
    if length < 0 or size < 0:
        raise ValueError("AXI len and size must be non-negative")
    return (length + 1) << size


def issuer_occupancy(service_cycles: int, length: int) -> int:
    """max(programmed service, beat count). The two terms are not added."""
    if service_cycles < 1:
        raise ValueError("programmed service cycles must be >= 1")
    beats = length + 1
    if beats < 1:
        raise ValueError("AXI beat count must be positive")
    return service_cycles if service_cycles > beats else beats


def retention_index(addr: int, granularity_bytes: int, sets: int) -> tuple[int, int]:
    if sets < 2 or (sets & (sets - 1)) != 0:
        raise ValueError("retention sets must be a power of two >= 2")
    if granularity_bytes < 1 or (granularity_bytes & (granularity_bytes - 1)) != 0:
        raise ValueError("retention granularity must be a positive power of two")
    gran_bits = granularity_bytes.bit_length() - 1
    set_bits = sets.bit_length() - 1
    index = (addr >> gran_bits) & (sets - 1)
    tag = addr >> (gran_bits + set_bits)
    return index, tag


def overlapping_services(log: list[dict]) -> list[tuple[dict, dict]]:
    """Pairs whose half-open [start, start+occupancy) windows overlap.

    A legal issuer schedule has none. This is the violation detector for a
    hand-written or captured admit log; the model is expected to emit none.
    """
    ordered = sorted(enumerate(log), key=lambda item: (item[1]["start"], item[0]))
    bad = []
    previous = None
    for _, event in ordered:
        if previous is not None and event["start"] < previous["start"] + previous["occupancy"]:
            bad.append((previous, event))
        if previous is None or event["start"] + event["occupancy"] > previous["start"] + previous["occupancy"]:
            previous = event
    return bad


@dataclass
class Access:
    addr: int
    axi_id: int = 0
    length: int = 0
    size: int = 3


@dataclass
class TechSpecModel:
    """One target-cycle step is one call to step(), starting at cycle 0."""

    read_latency: int = 30
    write_latency: int = 30
    read_service_cycles: int = 1
    write_service_cycles: int = 1
    read_max: int = 32
    write_max: int = 32
    endurance_limit_bytes: int = 0
    retention_cycles: int = 0
    retention_sets: int = 64
    retention_granularity_bytes: int = 64
    addr_bits: int = 32

    t_cycle: int = 0
    next_service: int = 0
    pending_reads: int = 0
    pending_aw: int = 0
    pending_w: int = 0
    device_read_bytes: int = 0
    device_write_bytes: int = 0
    logical_write_bytes: int = 0
    endurance_exceeded: bool = False
    admitted_reads: int = 0
    admitted_writes: int = 0
    issuer_busy_cycles: int = 0
    retention_fresh_reads: int = 0
    retention_stale_reads: int = 0
    retention_unknown_reads: int = 0
    schedule: list = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.read_latency < 1 or self.write_latency < 1:
            raise ValueError("latency must be >= 1")
        if self.read_max < 1 or self.write_max < 1:
            raise ValueError("outstanding caps must be >= 1")
        self._read_pipe: list[dict] = []
        self._write_pipe: list[dict] = []
        self._aw_queue: list[Access] = []
        self._retention: list[dict | None] = (
            [None] * self.retention_sets if self.retention_sets else []
        )
        if self.retention_sets:
            retention_index(0, self.retention_granularity_bytes, self.retention_sets)

    def _sat_update(self, value: int, inc: bool, dec: bool, maximum: int) -> int:
        full = value >= maximum
        empty = value == 0
        if inc and not dec and not full:
            return value + 1
        if not inc and dec and not empty:
            return value - 1
        return value

    def _next_head_release(self) -> int | None:
        releases = []
        if self._read_pipe:
            releases.append(self._read_pipe[0]["release"])
        if self._write_pipe:
            releases.append(self._write_pipe[0]["release"])
        return min(releases) if releases else None

    def has_inflight(self) -> bool:
        return bool(self._read_pipe or self._write_pipe)

    def _account_busy_range(self, start: int, end: int) -> None:
        if self.next_service > start:
            self.issuer_busy_cycles += min(end, self.next_service) - start

    def advance_to(self, target: int) -> None:
        """Move to target without executing it. Idle gaps keep the same counters
        as calling step() with no offers. A due response is executed.
        """
        if target < self.t_cycle:
            raise ValueError("cannot move backwards")
        while self.t_cycle < target:
            nxt = self._next_head_release()
            if nxt is not None and nxt <= self.t_cycle:
                self.step()
            elif nxt is not None and nxt < target:
                self._account_busy_range(self.t_cycle, nxt)
                self.t_cycle = nxt
                self.step()
            else:
                self._account_busy_range(self.t_cycle, target)
                self.t_cycle = target

    def step(
        self,
        ar: Access | None = None,
        aw: Access | None = None,
        w_last: bool = False,
        r_sink_ready: bool = True,
        b_sink_ready: bool = True,
    ) -> dict:
        cycle = self.t_cycle
        ar_ready = self.pending_reads < self.read_max
        aw_ready = self.pending_aw < self.write_max
        w_ready = self.pending_w < self.write_max

        take_ar = ar is not None and ar_ready
        take_aw = aw is not None and aw_ready
        take_w = w_last and w_ready

        # newWReq uses the pre-update pending counters, matching SplitTransactionModel.
        new_w = (
            (self.pending_w > self.pending_aw and take_aw)
            or (self.pending_w < self.pending_aw and take_w)
            or (take_w and take_aw)
        )

        read_event = None
        write_event = None
        if take_ar or new_w:
            base = cycle if cycle > self.next_service else self.next_service
            read_start = base
            if take_ar:
                read_occ = issuer_occupancy(self.read_service_cycles, ar.length)
                read_release = read_start + self.read_latency - EGRESS_UNIT_DELAY
                read_event = {
                    "cycle": cycle,
                    "kind": "R",
                    "addr": ar.addr,
                    "id": ar.axi_id,
                    "length": ar.length,
                    "size": ar.size,
                    "start": read_start,
                    "occupancy": read_occ,
                    "release": read_release,
                    "bytes": transfer_bytes(ar.length, ar.size),
                }
                self._read_pipe.append(read_event)
                self.schedule.append(read_event)
                self.device_read_bytes += read_event["bytes"]
                self.admitted_reads += 1
                self._classify_read(ar.addr, cycle)
            if new_w:
                if take_aw:
                    write_access = aw
                    self._aw_queue.append(aw)
                if not self._aw_queue:
                    raise RuntimeError("write admission without an address")
                # AW and W that complete a write leave the address queue together.
                write_access = self._aw_queue.pop(0)
                write_start = read_start + read_event["occupancy"] if read_event else base
                write_occ = issuer_occupancy(self.write_service_cycles, write_access.length)
                write_release = write_start + self.write_latency - EGRESS_UNIT_DELAY
                write_event = {
                    "cycle": cycle,
                    "kind": "W",
                    "addr": write_access.addr,
                    "id": write_access.axi_id,
                    "length": write_access.length,
                    "size": write_access.size,
                    "start": write_start,
                    "occupancy": write_occ,
                    "release": write_release,
                    "bytes": transfer_bytes(write_access.length, write_access.size),
                }
                self._write_pipe.append(write_event)
                self.schedule.append(write_event)
                nbytes = write_event["bytes"]
                if self.endurance_limit_bytes != 0 and self.device_write_bytes + nbytes > self.endurance_limit_bytes:
                    self.endurance_exceeded = True
                self.device_write_bytes += nbytes
                self.logical_write_bytes += nbytes
                self.admitted_writes += 1
                self._note_write(write_access.addr, cycle)
                self.next_service = write_start + write_occ
            else:
                self.next_service = read_event["start"] + read_event["occupancy"]
        elif take_aw:
            self._aw_queue.append(aw)

        completed_read = None
        if self._read_pipe and self._read_pipe[0]["release"] <= cycle and r_sink_ready:
            completed_read = self._read_pipe.pop(0)
        completed_write = None
        if self._write_pipe and self._write_pipe[0]["release"] <= cycle and b_sink_ready:
            completed_write = self._write_pipe.pop(0)

        self.pending_reads = self._sat_update(
            self.pending_reads, take_ar, completed_read is not None, self.read_max
        )
        self.pending_aw = self._sat_update(
            self.pending_aw, take_aw, completed_write is not None, self.write_max
        )
        self.pending_w = self._sat_update(
            self.pending_w, take_w, completed_write is not None, self.write_max
        )

        if cycle < self.next_service or take_ar or new_w:
            self.issuer_busy_cycles += 1

        self.t_cycle = cycle + 1
        return {
            "t_cycle": cycle,
            "ar_ready": ar_ready,
            "aw_ready": aw_ready,
            "w_ready": w_ready,
            "accepted_read": read_event,
            "accepted_write": write_event,
            "completed_read": completed_read,
            "completed_write": completed_write,
        }

    def _classify_read(self, addr: int, cycle: int) -> None:
        if self.retention_cycles == 0 or not self._retention:
            return
        index, tag = retention_index(addr, self.retention_granularity_bytes, self.retention_sets)
        entry = self._retention[index]
        if entry is None or entry["tag"] != tag:
            self.retention_unknown_reads += 1
            return
        age = cycle - entry["last_write"]
        if age > self.retention_cycles:
            self.retention_stale_reads += 1
        else:
            self.retention_fresh_reads += 1

    def _note_write(self, addr: int, cycle: int) -> None:
        if not self._retention:
            return
        index, tag = retention_index(addr, self.retention_granularity_bytes, self.retention_sets)
        self._retention[index] = {"tag": tag, "last_write": cycle}
