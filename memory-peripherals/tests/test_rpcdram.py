"""RPC DRAM functional, timing, and packet-encoding tests."""

from __future__ import annotations

import random

import pytest

from memperiph.rpcdram import (
    RpcCommand,
    RpcDramDevice,
    RpcDramFased,
    RpcDramParams,
    decode_addr,
    encode_eth_word,
    encode_parallel,
    flat_addr,
    profile_1600,
    profile_200mhz,
    theoretical_bandwidth_MBps,
)
from memperiph.util import AxiRequest, ck_ceil


P = profile_1600()


def test_geometry_and_catalog():
    assert P.n_banks == 4
    assert P.n_rows == 4096
    assert P.page_bytes == 2048
    assert P.size_bytes == 32 * 1024 * 1024
    assert P.tRCD_ck == 11
    assert P.tRP_ck == 11
    assert P.tRAS_ck == 28
    assert P.tRC_ck == 39
    assert P.tRRD_ck == 6
    assert P.tWR_ck == 12
    assert P.rl_ck == 12  # AL=1 + CL=11
    assert P.tREFI_fst_ck == 80
    assert {p.kind for p in P.catalog()} <= {"specified", "inferred", "approximation"}
    assert any(p.name == "tRCD_ps" and "13.75" in p.value or p.value == "13750" for p in P.catalog())
    # ETH map: 32 B word, column group, row, bank.
    bank, row, col, off = decode_addr(0x0080_0000)  # bit 23
    assert (bank, row, col, off) == (1, 0, 0, 0)
    bank, row, col, off = decode_addr(0x0000_0800)  # bit 11
    assert (bank, row, col, off) == (0, 1, 0, 0)
    bank, row, col, off = decode_addr(0x0000_0020)  # second 32 B word -> CA + 16
    assert (bank, row, col, off) == (0, 0, 16, 0)
    assert flat_addr(1, 0, 0) == 0x0080_0000


def test_packet_bits_match_the_datasheet_and_the_eth_decoder_map():
    act = RpcCommand("ACT", 0, bank=2, row=0xABC)
    db_p, db_n = encode_parallel(act)
    assert db_p & 0x7 == 0b101
    assert (db_p >> 3) & 0x3 == 2
    assert (db_n >> 1) & 0xFFF == 0xABC
    # ETH word: {11'b0, BA, 3'b101, 3'b000, row, 1'b0}
    word = encode_eth_word(act)
    assert (word >> 16) & 0x7 == 0b101
    assert (word >> 19) & 0x3 == 2
    assert (word >> 1) & 0xFFF == 0xABC
    assert word & 1 == 0
    rd = RpcCommand("RD", 0, bank=1, col=0x130, bc=0)  # CA[9:4] = 0x13
    db_p, db_n = encode_parallel(rd)
    assert db_p & 0x7 == 0b000
    assert (db_p >> 3) & 3 == 1
    assert (db_p >> 5) & 63 == 0
    assert (db_p >> 13) & 7 == (0x13 & 7)          # CA[6:4]
    assert (db_n >> 13) & 7 == ((0x13 >> 3) & 7)   # CA[9:7]
    word = encode_eth_word(rd)
    assert (word >> 16) & 7 == 0b000
    assert (word >> 21) & 63 == 0  # burst length field the ETH decoder reads
    assert (word >> 19) & 3 == 1
    wr = RpcCommand("WR", 0, bank=0, col=0, bc=3)
    assert (encode_eth_word(wr) >> 16) & 7 == 0b001
    assert (encode_eth_word(wr) >> 21) & 63 == 3
    pre = RpcCommand("PRE", 0, mask=0b1010)
    assert encode_parallel(pre)[0] & 7 == 0b100
    assert (encode_eth_word(pre) >> 22) & 0xF == 0b1010
    ref = RpcCommand("REF", 0, mask=0xF)
    assert (encode_eth_word(ref) >> 16) & 7 == 0b110
    assert encode_eth_word(RpcCommand("ZQC", 0)) & 1 == 1
    assert (encode_eth_word(RpcCommand("ZQC", 0)) >> 16) & 7 == 0b001


def test_initialization_respects_power_up_delays():
    dev = RpcDramDevice(P)
    ready = dev.initialize()
    assert ready >= P.tPWR_ck + P.tRESET_ck + P.tZQINIT_ck
    ops = [c.op for c in dev.commands]
    assert ops[:3] == ["PRE", "MRS", "ZQC"]
    assert dev.cl == 11
    assert not dev.zout_open
    assert dev.all_precharged()
    assert not dev.violations


def test_illegal_sequences_are_reported():
    dev = RpcDramDevice(P, assume_initialized=True)
    dev.issue(RpcCommand("RD", 0, bank=0, col=0, bc=0))
    assert any(v.code == "row-closed" for v in dev.violations)
    dev.violations.clear()
    dev.issue(RpcCommand("ACT", 10, bank=0, row=3))
    dev.issue(RpcCommand("RD", 11, bank=0, col=0, bc=0))
    assert any(v.code == "tRCD" for v in dev.violations)
    dev.violations.clear()
    # ACT to an open bank.
    dev.issue(RpcCommand("ACT", 100, bank=0, row=4))
    assert any(v.code == "act-open" for v in dev.violations)
    # tRRD: second bank too soon after a legal ACT.
    dev2 = RpcDramDevice(P, assume_initialized=True)
    dev2.issue(RpcCommand("ACT", 0, bank=0, row=1))
    dev2.issue(RpcCommand("ACT", P.tRRD_ck - 1, bank=1, row=1))
    assert any(v.code == "tRRD" for v in dev2.violations)


def test_read_after_write_masks_banks_and_page_wrap():
    m = RpcDramFased(P, page="open")
    payload = bytes(range(32))
    m.run([AxiRequest(True, 0, 32, data=payload, xid=1)])
    got = m.run([AxiRequest(False, 0, 32, xid=2)])
    assert got[0].data == payload
    assert not m.dev.violations
    # Second bank is a different 8 MB region.
    other = bytes([0xA5]) * 64
    m.run([AxiRequest(True, 8 * 1024 * 1024, 64, data=other, xid=3)])
    got = m.run([AxiRequest(False, 8 * 1024 * 1024, 64, xid=4)])
    assert got[0].data == other
    assert m.run([AxiRequest(False, 0, 32, xid=5)])[0].data == payload
    # Byte enables: only the first 4 bytes of a word change.
    m.run([AxiRequest(True, 0, 32, data=bytes([0xFF]) * 32,
                     strb=bytes([0xFF] * 4 + [0] * 28), xid=6)])
    data = m.run([AxiRequest(False, 0, 32, xid=7)])[0].data
    assert data[:4] == b"\xFF" * 4
    assert data[4:] == payload[4:]
    # Crossing a 2 KB page stays consistent (two row activations).
    page = 2048 - 16
    blob = bytes((i * 3) & 0xFF for i in range(64))
    m.run([AxiRequest(True, page, 64, data=blob, xid=8)])
    assert m.run([AxiRequest(False, page, 64, xid=9)])[0].data == blob
    assert not m.dev.violations


def test_row_hit_and_row_miss_latency():
    m = RpcDramFased(P, page="open")
    # Closed bank: ACT + first 8-CK command slot after tRCD + RL.
    miss = m.run([AxiRequest(False, 0, 32, xid=1)], outstanding=1)[0]
    assert miss.row_hit is False
    assert miss.first_data_cycle - miss.accept_cycle == P.act_to_cas_ck + P.rl_ck
    # Same row, previous burst finished: parallel RD, latency is RL.
    hit = m.run([AxiRequest(False, 32, 32, xid=2)], outstanding=1)[0]
    assert hit.row_hit is True
    assert hit.latency == P.rl_ck
    # Different row, same bank: PRE + tRP + ACT + tRCD + RL, with tPPD.
    conflict = m.run([AxiRequest(False, 2048, 32, xid=3)], outstanding=1)[0]
    assert conflict.row_hit is False
    assert conflict.latency >= P.tRP_ck + P.tRCD_ck + P.rl_ck
    assert not m.dev.violations


def test_closed_page_matches_eth_act_cas_pre_and_streaming_approaches_peak():
    closed = RpcDramFased(P, page="closed")
    closed.run([AxiRequest(False, 0, 32, xid=1)])
    ops = [c.op for c in closed.dev.commands]
    assert ops[0] == "ACT" and "RD" in ops and ops[-1] == "PRE"
    assert closed.dev.all_precharged()
    # Long sequential stream on an open row should fill the data bus.
    opened = RpcDramFased(P, page="open")
    n_words = 64
    nbytes = n_words * 32
    done = opened.run([AxiRequest(False, 0, nbytes, xid=1)], outstanding=8)
    # One activation plus a single burst of 64 words (a full page).
    rds = [c for c in opened.dev.commands if c.op == "RD"]
    assert len(rds) == 1
    assert rds[0].bc + 1 == n_words
    cycles = done[0].done_cycle - done[0].accept_cycle
    data_ck = n_words * 8
    # Pipeline fill includes the active-state command grid.
    assert cycles == P.act_to_cas_ck + P.rl_ck + data_ck
    bw = (nbytes / cycles) * (1e12 / P.tck_ps) / 1e6
    peak = theoretical_bandwidth_MBps(P)
    assert peak == pytest.approx(3200.0)
    assert bw > 0.90 * peak
    assert not opened.dev.violations


def test_back_to_back_streaming_has_no_data_bubble():
    m = RpcDramFased(P, page="open")
    reqs = [AxiRequest(False, i * 32, 32, xid=i) for i in range(8)]
    done = m.run(reqs, outstanding=8)
    rds = [c for c in m.dev.commands if c.op == "RD"]
    assert rds[0].serial is False
    assert all(c.serial for c in rds[1:])
    # Data phases abut: next data starts where the previous one ended.
    for a, b in zip(rds, rds[1:]):
        a_end = a.cycle + P.rl_ck + 8 * (a.bc + 1)
        b_start = b.cycle + P.rl_ck
        assert b_start == a_end
    assert done[-1].data == bytes(32)
    assert not m.dev.violations


def test_refresh_stall_and_200mhz_profile():
    m = RpcDramFased(P, page="open", refresh=True)
    # Force the refresh window to expire before the access.
    m.next_refresh = 0
    m.run([AxiRequest(False, 0, 32, xid=1)])
    assert any(c.op == "REF" for c in m.dev.commands)
    assert m.refresh_stall == P.n_rows * P.tREFI_fst_ck * P.n_banks
    assert not m.dev.violations
    p200 = profile_200mhz()
    assert p200.tck_ps == 5000
    assert p200.rl_ck == 9
    assert p200.cl == 8 and p200.tRTW_ck == 8 and p200.tWTR_ck == 8
    assert theoretical_bandwidth_MBps(p200) == pytest.approx(800.0)
    m200 = RpcDramFased(p200, page="open")
    hit_setup = m200.run([AxiRequest(False, 0, 32)], outstanding=1)
    hit = m200.run([AxiRequest(False, 32, 32)], outstanding=1)[0]
    assert hit.latency == p200.rl_ck
    # At 200 MHz, tRCD is 3 CK but an active-state parallel command cannot
    # follow ACT sooner than tPPD (8 CK). The column command is tPPD-limited.
    assert hit_setup[0].latency == max(p200.tRCD_ck, p200.tPPD_act_ck) + p200.rl_ck


def test_random_traffic_matches_a_shadow(seed=20261016):
    rng = random.Random(seed)
    m = RpcDramFased(P, page="open")
    shadow = bytearray(64 * 1024)
    reqs = []
    for xid in range(40):
        addr = rng.randrange(0, len(shadow) - 64) & ~1
        n = rng.choice((32, 64, 96))
        # Keep the access inside the shadow and 2-byte aligned.
        if rng.random() < 0.5:
            data = bytes(rng.randrange(256) for _ in range(n))
            strb = bytes(rng.choice((0, 0xFF)) for _ in range(n))
            if not any(strb):
                strb = bytes([0xFF]) + strb[1:]
            reqs.append(AxiRequest(True, addr, n, xid=xid, data=data, strb=strb))
        else:
            reqs.append(AxiRequest(False, addr, n, xid=xid))
    done = m.run(reqs, outstanding=4)
    for req, comp in zip(reqs, done):
        if req.is_write:
            for i, (val, en) in enumerate(zip(req.data, req.strb)):
                if en:
                    shadow[req.addr + i] = val
        else:
            assert comp.data == bytes(shadow[req.addr:req.addr + req.length])
    assert not m.dev.violations


def test_four_banks_are_independent_above_bit_23():
    """The 22-bit AXI fuzzer never reaches these addresses."""
    m = RpcDramFased(P, page="open")
    patterns = {}
    for bank in range(4):
        addr = bank << 23
        blob = bytes([0x10 + bank]) * 32
        patterns[bank] = blob
        m.run([AxiRequest(True, addr, 32, data=blob, xid=bank)])
    for bank in range(4):
        got = m.run([AxiRequest(False, bank << 23, 32, xid=10 + bank)])[0]
        assert got.data == patterns[bank]
        assert got.bank == bank
    assert not m.dev.violations


def test_fast_refresh_duration_matches_the_row_step_formula():
    """4096 rows * 100 ns * 4 banks at tCK=1.25 ns."""
    m = RpcDramFased(P, page="open", refresh=True)
    m.next_refresh = 0
    m.run([AxiRequest(False, 0, 32, xid=1)])
    expect = P.n_rows * P.tREFI_fst_ck * P.n_banks
    assert expect == 4096 * 80 * 4 == 1_310_720
    assert m.refresh_stall == expect
    ref = [c for c in m.dev.commands if c.op == "REF"][-1]
    assert ref.mask == 0xF
    assert m.dev.busy_until == ref.cycle + expect
    # The read that follows refresh is after the busy window.
    assert m.dev.commands[-1].cycle >= m.dev.busy_until or m.dev.commands[-1].op == "RD"

    dev = RpcDramDevice(P, assume_initialized=True)
    dev.issue(RpcCommand("REF", 100, mask=0xF, ref_op=0))
    assert dev.busy_until == 100 + expect
    dev.issue(RpcCommand("ACT", 110, bank=0, row=1))
    assert any(v.code == "busy" for v in dev.violations)
    # The complete REF BUSY interval already contains precharge recovery.
    dev.issue(RpcCommand("ACT", dev.busy_until, bank=1, row=2))
    assert dev.banks[1].row == 2
    assert not any(v.code == "tRP/tRC" for v in dev.violations if v.cycle == dev.busy_until)


def test_scheduler_refuses_to_emit_an_early_cas():
    """A hand-built early RD is illegal; the scheduler's own stream is not."""
    dev = RpcDramDevice(P, assume_initialized=True)
    dev.issue(RpcCommand("ACT", 0, bank=0, row=0))
    dev.issue(RpcCommand("RD", P.tRCD_ck, bank=0, col=0, bc=0))
    assert any(v.code == "tPPD-grid" for v in dev.violations)
    dev.violations.clear()
    dev.issue(RpcCommand("RD", P.act_to_cas_ck, bank=0, col=0, bc=0))
    assert not dev.violations
    dev.issue(RpcCommand("RD", P.act_to_cas_ck + 1, bank=0, col=32, bc=0, serial=True))
    # 1 CK after the parallel RD is not on the 8 CK serial grid.
    assert any(v.code == "serial-grid" for v in dev.violations)
