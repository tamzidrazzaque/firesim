"""Refresh occupancy readings. Neither number is a named tRFC."""

from __future__ import annotations

from .params import GEOMETRY, P

# Section 5: LP refresh of four banks "will take 64 ms", and above 85 C only
# one or two banks may be selected. 64 ms is also tRET. The row-step product
# is 52.429 ms, not 64 ms. The hot limit distinguishes the two readings.
RETENTION_MS = 64
RETENTION_HOT_MS = 32
LP_TREFI_NS = 3_200


def row_step_cycles(step_cycles: int, n_banks: int, n_rows: int = GEOMETRY.rows) -> int:
    if n_banks < 1 or n_rows < 1 or step_cycles < 1:
        raise ValueError((step_cycles, n_banks, n_rows))
    return n_rows * step_cycles * n_banks


def row_step_ns(trefi_ns: float, n_banks: int, n_rows: int = GEOMETRY.rows) -> float:
    return n_rows * trefi_ns * n_banks


def one_trefi_cycles(step_cycles: int) -> int:
    return step_cycles


def lp_bank_limit_matches_hot_retention() -> dict[int, bool]:
    """True when n_banks * 4096 * 3.2 us is still inside the 32 ms hot limit."""
    return {
        n: row_step_ns(LP_TREFI_NS, n) / 1e6 <= RETENTION_HOT_MS
        for n in (1, 2, 3, 4)
    }
