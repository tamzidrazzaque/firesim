"""Replay pin-command timestamps through the independent timing model.

The checker does not move an early command to a later cycle. A rejected
command leaves bank state unchanged, which is the device rule in `device.py`.
Write payloads are not on the command packet; the replay supplies zeros of
the legal length so a missing data beat is not reported as a timing error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .device import Command, RpcDram, Violation
from .packets import SECTIONS, decode_packet
from .profiles import ClockProfile, profile_for

PIN_CMD = re.compile(
    r"RPC_PIN_CMD cycle=(\d+) packet=([0-9a-fA-F]+)"
)


@dataclass(frozen=True)
class Observed:
    cycle: int
    packet: int
    command: Command


@dataclass(frozen=True)
class ViolationReport:
    constraint: str
    command: str
    bank: int | None
    row: int | None
    offered_cycle: int
    earliest_legal_cycle: int | None
    previous: str
    section: str
    detail: str

    def format(self) -> str:
        earliest = (
            "none"
            if self.earliest_legal_cycle is None
            else str(self.earliest_legal_cycle)
        )
        return (
            f"{self.constraint} {self.command} bank={self.bank} row={self.row} "
            f"offered={self.offered_cycle} earliest={earliest} "
            f"previous={self.previous} section={self.section} {self.detail}"
        ).rstrip()


def parse_pin_log(text: str) -> list[Observed]:
    found: list[Observed] = []
    for line in text.splitlines():
        match = PIN_CMD.search(line)
        if match is None:
            continue
        cycle = int(match.group(1))
        packet = int(match.group(2), 16)
        found.append(Observed(cycle, packet, decode_packet(packet, cycle)))
    return found


def _previous_text(command: Command | None) -> str:
    if command is None:
        return "none"
    return (
        f"{command.kind}@{command.cycle} bank={command.bank} row={command.row}"
    )


def replay(
    observed: list[Observed],
    profile: ClockProfile,
    *,
    page_policy: str = "closed",
    refresh_occupancy: str = "one_trefi",
) -> tuple[RpcDram, list[ViolationReport], dict[str, int]]:
    device = RpcDram(
        page_policy=page_policy,
        timing=profile,
        refresh_occupancy=refresh_occupancy,
    )
    reports: list[ViolationReport] = []
    counts: dict[str, int] = {}
    last: Command | None = None
    for item in observed:
        counts[item.command.kind] = counts.get(item.command.kind, 0) + 1
        result = device.issue(item.command)
        if result.accepted:
            last = item.command
            continue
        for violation in result.violations:
            reports.append(_report(item.command, violation, last))
    return device, reports, counts


def _report(command: Command, violation: Violation, previous: Command | None) -> ViolationReport:
    return ViolationReport(
        constraint=violation.constraint,
        command=command.kind,
        bank=command.bank,
        row=command.row,
        offered_cycle=violation.offered_cycle,
        earliest_legal_cycle=violation.earliest_legal_cycle,
        previous=_previous_text(previous),
        section=SECTIONS.get(violation.constraint, "see the independent model README"),
        detail=violation.detail,
    )


def shift_first_column(observed: list[Observed], earliest_delta: int) -> list[Observed]:
    """Move the first READ or WRITE to ACT + earliest_delta - 1.

    The packet bits stay the same. Only the offered cycle changes, and only
    when that cycle is still at or after the previous command.
    """
    act_at: dict[int, int] = {}
    previous_cycle = -1
    shifted: list[Observed] = []
    done = False
    for item in observed:
        command = item.command
        cycle = item.cycle
        if not done and command.kind == "activate" and command.bank is not None:
            act_at[command.bank] = cycle
        if (
            not done
            and command.kind in ("read", "write")
            and command.bank in act_at
        ):
            offered = act_at[command.bank] + earliest_delta - 1
            if previous_cycle <= offered < cycle:
                cycle = offered
                command = decode_packet(item.packet, cycle)
                done = True
        shifted.append(Observed(cycle, item.packet, command))
        previous_cycle = cycle
    if not done:
        raise RuntimeError("no column command could be moved earlier")
    return shifted
