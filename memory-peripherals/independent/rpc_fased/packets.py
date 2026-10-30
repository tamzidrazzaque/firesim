"""Decode one 32-bit parallel request packet.

Table 7-1 lists two DB beats. The integer used by the pin trace is
{first beat, second beat}. Opcode is DB[2:0] of the first beat.

RESET and ZQ share the READ and WRITE opcodes. Section 7 and Tables 7-4
distinguish them by DB[0] of the second beat.
"""

from __future__ import annotations

from .device import (
    Activate,
    Command,
    ModeRegister,
    Precharge,
    Read,
    Refresh,
    Reset,
    Write,
    ZqCal,
)

CL_CODE = {0b000: 8, 0b001: 10, 0b010: 11, 0b110: 3}
NWR_CODE = {
    0b000: 4,
    0b001: 6,
    0b010: 7,
    0b011: 8,
    0b100: 10,
    0b101: 12,
    0b110: 14,
    0b111: 16,
}
ZQ_KIND = {0b00: "init", 0b01: "long", 0b10: "short", 0b11: "reset"}

SECTIONS = {
    "tRCD": "Table 11-3, ACT to internal read or write",
    "tRP": "Table 11-3, PRE command period",
    "tRAS": "Table 11-3, ACTIVE to PRECHARGE",
    "tRC": "Table 11-3, ACT to ACT or REF",
    "tRRD": "Table 11-3, ACTIVE to ACTIVE",
    "tWR": "Table 11-3 and Figure 12-3, write recovery",
    "nWR": "Table 7-2 nWR field versus Table 11-3 tWR",
    "tWTR": "Table 11-3, write burst to read burst",
    "tRTW": "Table 11-3, read burst to write burst",
    "tPPD": "Table 11-3 and Figure 12-1, parallel command spacing",
    "tPPD_grid": "Section 2.8 and Table 11-3, active-state 8-CK command grid",
    "tCCD": "Section 2.4, WORD burst occupancy",
    "tMRD": "Table 11-3, MRS to MRS",
    "tMOD": "Table 11-3, MRS update delay",
    "tRESET": "Table 11-3 and Section 4, reset exit",
    "tREFI": "Section 5 and Table 11-3, one-shot refresh busy window",
    "tZQINIT": "Table 11-3, initialization calibration",
    "tZQCL": "Table 11-3, long calibration",
    "tZQCS": "Table 11-3, short calibration",
    "tZQRESET": "Table 11-3, ZQ reset",
    "read_to_precharge": "Figure 12-11, precharge at the end of read data (no tRTP symbol)",
    "init_reset": "Section 4, reset before any other command",
    "init_precharge": "Section 4, precharge-all after reset",
    "init_mrs": "Section 4, MRS after precharge-all",
    "CL": "Table 7-2 and Table 11-3 speed column",
    "row_open": "Section 2.5, a column command needs an open row",
    "require_active_bank": "Table 8-3, PRE targets an open bank",
    "require_idle_bank": "Table 7-1 ACT, bank must be idle",
}


def column_of(rise: int, fall: int) -> int:
    """CA[4:9] as a 0..63 WORD index. CA[0:3] are not applied (note 2)."""
    ca4 = (rise >> 13) & 0x7
    ca7 = (fall >> 13) & 0x7
    return (ca7 << 3) | ca4


def decode_packet(packet: int, cycle: int) -> Command:
    if packet < 0 or packet > 0xFFFFFFFF:
        raise ValueError(hex(packet))
    rise = (packet >> 16) & 0xFFFF
    fall = packet & 0xFFFF
    op = rise & 0x7
    bank = (rise >> 3) & 0x3
    if op == 0b000 and fall == 1 and rise == 0:
        return Reset(cycle)
    if op == 0b000:
        return Read(cycle, bank, column_of(rise, fall), burst_count=(rise >> 5) & 0x3F)
    if op == 0b001 and (fall & 1) == 1:
        return ZqCal(cycle, ZQ_KIND[(rise >> 14) & 0x3])
    if op == 0b001:
        bc = (rise >> 5) & 0x3F
        return Write(
            cycle,
            bank,
            column_of(rise, fall),
            bytes((bc + 1) * 32),
            burst_count=bc,
        )
    if op == 0b010:
        cl_code = (rise >> 3) & 0x7
        nwr_code = (rise >> 6) & 0x7
        if cl_code not in CL_CODE or nwr_code not in NWR_CODE:
            raise ValueError(f"MRS field at cycle {cycle}: packet {packet:#010x}")
        return ModeRegister(
            cycle,
            cl=CL_CODE[cl_code],
            nwr=NWR_CODE[nwr_code],
            zout=(rise >> 9) & 0xF,
            csrfx=(fall >> 13) & 1,
            refop=(fall >> 1) & 0x3,
        )
    if op == 0b100:
        mask = (rise >> 6) & 0xF
        if mask == 0xF:
            return Precharge(cycle, all_banks=True)
        if mask.bit_count() != 1:
            raise ValueError(f"PRE mask {mask:#x} at cycle {cycle} is not one bank or all banks")
        return Precharge(cycle, mask.bit_length() - 1)
    if op == 0b101:
        return Activate(cycle, bank, (fall >> 1) & 0xFFF)
    if op == 0b110:
        mask = (rise >> 6) & 0xF
        banks = tuple(index for index in range(4) if mask & (1 << index))
        return Refresh(cycle, banks, refop=(fall >> 1) & 0x3)
    raise ValueError(f"opcode {op} at cycle {cycle} packet {packet:#010x}")
