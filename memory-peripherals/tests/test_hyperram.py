"""HyperRAM functional and timing tests.

Expected cycles are computed from the published 200 MHz numbers in the test,
not by calling the model to predict itself.
"""

from __future__ import annotations

import random

import pytest

from memperiph.hyperram import (
    REG_CR0,
    REG_CR1,
    REG_ID0,
    HyperRAMDevice,
    HyperRAMFased,
    HyperRAMParams,
    theoretical_bandwidth_MBps,
)
from memperiph.util import AxiRequest, ck_ceil


P = HyperRAMParams()


def spec_gap_ck(prev: str | None, direction: str) -> int:
    if prev == "R" and direction == "W":
        return max(ck_ceil(P.tRWR_ps, P.tck_ps), ck_ceil(P.tCSHI_ps, P.tck_ps))
    if prev is None:
        return 0
    return ck_ceil(P.tCSHI_ps, P.tck_ps)


def test_catalog_covers_every_default():
    kinds = {p.kind for p in P.catalog()}
    assert kinds <= {"specified", "inferred", "approximation"}
    names = {p.name for p in P.catalog()}
    for required in ("tCK", "tCSHI", "tRWR", "tCSM", "tACC", "ca"):
        assert any(required.lower() in n.lower() or required.lower() in p.name.lower()
                   for n in names for p in P.catalog())
    assert any(p.name == "tCSHI_ps" and p.kind == "specified" for p in P.catalog())


def test_power_on_defaults_and_reset_timing():
    dev = HyperRAMDevice()
    assert dev.cr0 == 0x8F2F
    assert dev.latency_code_ck() == 7
    assert dev.fixed_latency
    assert not dev.hybrid
    assert dev.wrap_bytes() == 32
    assert dev.p.n_rows == 32768
    # Explicit reset spends tRP + tRH.
    t_rp = ck_ceil(P.tRP_ps, P.tck_ps)
    t_rh = ck_ceil(P.tRH_ps, P.tck_ps)
    assert t_rp == 40 and t_rh == 40
    done = dev.power_on_reset()
    assert done == t_rp + t_rh
    assert dev.cr0 == 0x8F2F
    # A transaction issued before the reset completes is pushed out or flagged.
    early = HyperRAMDevice()
    early.cycle = 0
    early.reset_done = False
    early.transaction(False, 0, 2, obey_timing=True)
    assert any(v.code == "reset" for v in early.violations)


def test_read_after_write_and_masks():
    dev = HyperRAMDevice()
    payload = bytes(range(32))
    wr = dev.write(0, payload)
    rd = dev.read(0, 32)
    assert rd.data == payload
    assert wr.done < dev.history[-1].start
    # Odd bytes masked (RWDS high). Memory keeps the previous odd bytes.
    masked = bytes([0xA0 + i for i in range(8)])
    enable = bytes([0xFF, 0x00] * 4)
    dev.write(64, b"\x11" * 8)
    dev.write(64, masked, enable)
    got = dev.read(64, 8)
    expect = bytes([masked[i] if enable[i] else 0x11 for i in range(8)])
    assert got.data == expect


def test_linear_wrap_hybrid_and_capacity():
    dev = HyperRAMDevice()
    # Legacy wrapped 32 B burst, start at offset 16.
    dev.cr0 = 0x8F27  # variable, legacy (bit2=1), 32 B wrap, latency code 2
    assert dev.wrap_bytes() == 32 and not dev.hybrid
    dev.mem.write(0, bytes(range(32)))
    wrapped = dev.read(16, 32, linear=False)
    expect = bytes(range(16, 32)) + bytes(range(0, 16))
    assert wrapped.data == expect
    # Linear crosses the wrap group.
    linear = dev.read(16, 32, linear=True)
    assert linear.data == dev.mem.read(16, 32)
    # Hybrid: first 32 wrap, then linear past the group.
    dev.cr0 &= ~0x4
    assert dev.hybrid
    dev.mem.write(32, bytes([0x5A]) * 16)
    hybrid = dev.read(16, 48, linear=False)
    assert hybrid.data[:32] == expect
    assert hybrid.data[32:] == bytes([0x5A]) * 16
    # CA[45]=1 stays linear even with CR0 hybrid sequencing enabled.
    assert dev.read(16, 48, linear=True).data == dev.mem.read(16, 48)
    # A linear burst across the last array word wraps to address zero.
    dev.cr0 |= 0x4
    assert not dev.hybrid
    tail = dev.p.size_bytes - 4
    dev.write(tail, b"\xAB\xCD\xEF\x01")
    assert dev.read(tail, 4).data == b"\xAB\xCD\xEF\x01"
    assert dev.read(dev.p.size_bytes - 2, 4, linear=True).data == b"\xEF\x01\x00\x01"
    assert not any(v.code == "addr" for v in dev.violations)


def test_registers_are_sticky_and_id_is_readonly():
    dev = HyperRAMDevice()
    cr0_addr = REG_CR0 * 2
    raw = dev.read(cr0_addr, 2, space="reg")
    assert raw.data == bytes([(dev.cr0 >> 8) & 0xFF, dev.cr0 & 0xFF])
    # Switch to variable latency, code still 7, legacy 32 B.
    new = 0x8F27
    dev.write(cr0_addr, bytes([(new >> 8) & 0xFF, new & 0xFF]), space="reg")
    assert dev.cr0 == new
    assert not dev.fixed_latency
    assert dev.latency_code_ck() == 7
    assert dev.id0 == 0x0E86
    raw_id = dev.read(REG_ID0 * 2, 2, space="reg")
    assert raw_id.data == b"\x0e\x86"
    assert dev.read(REG_ID0 * 2, 4, space="reg").data == b"\x0e\x86\x0e\x86"
    id_before = dev.id0
    dev.write(REG_ID0 * 2, b"\x12\x34", space="reg")
    assert dev.id0 == id_before
    assert any(v.code == "id-ro" for v in dev.violations)
    # CR1 partial-array select: bottom eighth.
    cr1 = (dev.cr1 & ~(0x7 << 2)) | (0b011 << 2)
    dev.write(REG_CR1 * 2, bytes([(cr1 >> 8) & 0xFF, cr1 & 0xFF]), space="reg")
    assert dev.covered_rows() == dev.p.n_rows // 8


def test_register_write_zero_latency_and_unmasked_single_word():
    dev = HyperRAMDevice()
    cr0_addr = REG_CR0 * 2
    wr = dev.write(cr0_addr, b"\x8f\x27", space="reg")
    assert wr.first_data == wr.start + 3
    assert wr.cs_low_ck == 4
    before = dev.cr0
    dev.write(cr0_addr, b"\x8f\x2f", b"\xff\x00", space="reg")
    assert dev.cr0 == before
    assert any(v.code == "reg-mask" for v in dev.violations)
    dev.write(cr0_addr, b"\x8f\x2f\x12\x34", space="reg")
    assert dev.cr0 == before
    assert any(v.code == "reg-length" for v in dev.violations)
    dev.write(cr0_addr, b"\x80\x27", space="reg")
    assert dev.cr0 == before
    assert any(v.code == "cr0-reserved" for v in dev.violations)
    cr1_addr = REG_CR1 * 2
    dev.write(cr1_addr, b"\xff\xc2", space="reg")
    assert dev.cr1 == 0xFFC1
    assert any(v.code == "cr1-readonly" for v in dev.violations)


def test_fixed_and_variable_latency_match_the_spec():
    dev = HyperRAMDevice()
    # Fixed latency (power-on): 2 * 7 CK after the 3 CK CA phase.
    txn = dev.read(0, 32)
    assert txn.rwds_high
    assert txn.latency_ck == 14
    assert txn.first_data == 0 + 3 + 14
    assert txn.done == 0 + 3 + 14 + 16
    assert txn.cs_low_ck == 3 + 14 + 16
    # Variable latency, caught up, no collision on the next access: 7 CK.
    dev.write(REG_CR0 * 2, bytes([0x8F, 0x27]), space="reg")
    assert not dev.fixed_latency
    txn = dev.read(0, 32)
    assert txn.latency_ck == 7
    assert not txn.rwds_high
    assert txn.first_data == txn.start + 3 + 7


def test_read_to_write_gap_is_tRWR_and_same_direction_is_tCSHI():
    dev = HyperRAMDevice()
    dev.write(REG_CR0 * 2, bytes([0x8F, 0x27]), space="reg")
    rd = dev.read(0, 2)
    # The write is stalled until tRWR.
    wr = dev.write(2, b"\x01\x02")
    need = spec_gap_ck("R", "W")
    assert need == ck_ceil(P.tRWR_ps, P.tck_ps) == 7
    assert wr.start - rd.done == need
    wr2 = dev.write(4, b"\x03\x04")
    assert wr2.start - wr.done == ck_ceil(P.tCSHI_ps, P.tck_ps) == 2


def test_short_gap_is_a_violation_and_tcsm_is_enforced():
    dev = HyperRAMDevice()
    dev.read(0, 2)
    rise = dev._cs_rise
    # Force the clock back into the tCSHI window.
    dev.cycle = rise + 1
    dev.read(0, 2, obey_timing=False)
    assert any(v.code == "cs-high" for v in dev.violations)
    # One CS# longer than tCSM.
    huge = (P.tCSM_ck + 10) * 2
    dev.read(0, huge)
    assert any(v.code == "tCSM" for v in dev.violations)
    # The FASED splitter keeps every chip-select legal.
    fased = HyperRAMFased()
    fased.dev.write(REG_CR0 * 2, bytes([0x8F, 0x27]), space="reg")
    fased.dev.violations.clear()
    req = AxiRequest(False, 0, 4096, issue=0, xid=1)
    done = fased.run([req])
    assert done[0].data == bytes(4096)
    assert not any(v.code == "tCSM" for v in fased.dev.violations)
    assert all(t.cs_low_ck <= P.tCSM_ck for t in fased.dev.history)


def test_refresh_collision_appears_only_after_the_debt_builds():
    dev = HyperRAMDevice()
    dev.write(REG_CR0 * 2, bytes([0x8F, 0x27]), space="reg")
    # Independent accounting: each minimum read is CS-low = 3+7+1 = 11 CK
    # of a 2-byte read, then tCSHI = 2 CK high, which is shorter than tRFH
    # so the gap retires nothing.
    assert P.tRFH_ck == 7
    assert P.tCSHI_ck == 2
    extras = []
    for i in range(400):
        txn = dev.read(0, 2)
        extras.append(txn.rwds_high)
    assert extras[0] is False
    assert any(extras), "a refresh collision should eventually be signaled"
    first = extras.index(True)
    # The collision must not be on the first access, and RWDS must be high
    # exactly when the doubled latency is used.
    assert first > 0
    doubled = [t.latency_ck == 14 for t in dev.history if t.space == "mem"]
    assert doubled[first] is True
    # A long idle gap lets the device catch up; the next access is 1x.
    dev.wait(2 * P.tCSM_ck)
    caught = dev.read(0, 2)
    assert caught.latency_ck == 7
    assert not caught.rwds_high


def test_fased_ordering_back_to_back_and_random_seed():
    rng = random.Random(0xC0FFEE)
    fased = HyperRAMFased()
    fased.dev.write(REG_CR0 * 2, bytes([0x8F, 0x27]), space="reg")
    fased.dev.violations.clear()
    image = {addr: rng.randrange(256) for addr in range(0, 4096, 1)}
    # Program the array directly, then check reads through the model.
    for addr, val in image.items():
        fased.dev.mem.write(addr, bytes([val]))
    reqs = []
    xid = 0
    # Sequential writes, then reads, then a mixed random set.
    seq = bytes(rng.randrange(256) for _ in range(256))
    reqs.append(AxiRequest(True, 0x1000, len(seq), issue=0, xid=xid, data=seq))
    xid += 1
    reqs.append(AxiRequest(False, 0x1000, len(seq), issue=0, xid=xid))
    xid += 1
    for _ in range(20):
        addr = rng.randrange(0, 3000) & ~1
        n = rng.choice((2, 8, 32, 64))
        if rng.random() < 0.5:
            data = bytes(rng.randrange(256) for _ in range(n))
            reqs.append(AxiRequest(True, addr, n, issue=0, xid=xid, data=data))
        else:
            reqs.append(AxiRequest(False, addr, n, issue=0, xid=xid))
        xid += 1
    done = fased.run(reqs, outstanding=4)
    assert [c.xid for c in done] == list(range(len(reqs)))
    # Replay the same requests against a shadow array to check data.
    shadow = dict(image)
    for req, comp in zip(reqs, done):
        if req.is_write:
            for i, (val, en) in enumerate(zip(req.data, req.strb)):
                if en:
                    shadow[req.addr + i] = val
            assert comp.done_cycle >= comp.accept_cycle
        else:
            expect = bytes(shadow.get(req.addr + i, 0) for i in range(req.length))
            assert comp.data == expect
    assert fased.trace[0].startswith("HYPERREQ,")
    assert theoretical_bandwidth_MBps() == pytest.approx(400.0)


def test_id0_matches_s80ks2562_section_6_2_1():
    dev = HyperRAMDevice()
    assert dev.id0 == 0x0E86
    assert dev.read(REG_ID0 * 2, 2, space="reg").data == bytes([0x0E, 0x86])


def test_two_kib_read_is_split_to_honor_tcsm():
    """A single 2 KiB chip-select is 5.12 us of data at 200 MHz, above both tCSM columns."""
    p = HyperRAMParams()
    assert p.tCSM_ck == 800  # 4 us at 5 ns
    data_ck = 2048 // 2
    assert data_ck * p.tck_ps == 5_120_000
    fased = HyperRAMFased()
    fased.dev.write(REG_CR0 * 2, bytes([0x8F, 0x27]), space="reg")  # variable, L=7
    fased.dev.violations.clear()
    fased.dev.history.clear()
    done = fased.run([AxiRequest(False, 0, 2048)])
    assert done[0].data == bytes(2048)
    mem = [t for t in fased.dev.history if t.space == "mem"]
    assert len(mem) >= 2
    assert all(t.cs_low_ck <= p.tCSM_ck for t in mem)
    assert not any(v.code == "tCSM" for v in fased.dev.violations)
    # Hot column, Tc > 85 C: tCSM = 1 us = 200 CK. Still legal, more splits.
    hot = HyperRAMParams(tCSM_ps=1_000_000)
    assert hot.tCSM_ck == 200
    hf = HyperRAMFased(hot)
    hf.dev.write(REG_CR0 * 2, bytes([0x8F, 0x27]), space="reg")
    hf.dev.history.clear()
    hf.run([AxiRequest(False, 0, 2048)])
    hot_mem = [t for t in hf.dev.history if t.space == "mem"]
    assert len(hot_mem) > len(mem)
    assert all(t.cs_low_ck <= hot.tCSM_ck for t in hot_mem)


def test_deep_power_down_blocks_memory_until_reset():
    dev = HyperRAMDevice()
    cr0 = dev.cr0 & ~0x8000
    dev.write(REG_CR0 * 2, bytes([(cr0 >> 8) & 0xFF, cr0 & 0xFF]), space="reg")
    assert dev.dpd
    dev.read(0, 2)
    assert any(v.code == "dpd" for v in dev.violations)
    dev.reset_pulse()
    assert not dev.dpd
    assert dev.read(0, 2).data == b"\x00\x00"
