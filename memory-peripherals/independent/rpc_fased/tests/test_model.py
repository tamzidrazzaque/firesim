"""Functional and timing tests for the speed-1600 RPC DRAM model."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rpc_fased import (
    Activate,
    Command,
    ModeRegister,
    P,
    Precharge,
    Read,
    Refresh,
    RefreshExit,
    Reset,
    RpcDram,
    Write,
    ZqCal,
)
from rpc_fased.device import ENFORCED_CONSTRAINTS

EXERCISED: set[str] = set()


def tearDownModule():
    missing = ENFORCED_CONSTRAINTS - EXERCISED
    extra = EXERCISED - ENFORCED_CONSTRAINTS
    if missing or extra:
        raise AssertionError(f"missing={sorted(missing)} extra={sorted(extra)}")


class ModelTest(unittest.TestCase):
    def up(self, **kwargs) -> tuple[RpcDram, int]:
        policy = kwargs.pop("page_policy", "open")
        dev = RpcDram(page_policy=policy)
        return dev, dev.initialize(**kwargs)

    def expect(self, result, name: str, earliest: int | None) -> None:
        EXERCISED.add(name)
        self.assertFalse(result.accepted, result.violations)
        self.assertIsNone(result.data)
        matches = [
            v
            for v in result.violations
            if v.constraint == name
            and v.earliest_legal_cycle == earliest
            and v.offered_cycle == result.offered_cycle
        ]
        self.assertTrue(
            matches,
            f"wanted {name} earliest={earliest}, got {result.violations}",
        )


class TestFunctional(ModelTest):
    def test_read_after_write_and_early_write_is_not_delayed(self):
        dev, t0 = self.up()
        self.assertTrue(dev.issue(Activate(t0, 0, 4)).accepted)
        early_cycle = t0 + P.tRCD - 1
        early = dev.issue(Write(early_cycle, 0, 3, bytes([0xAB]) * 32))
        self.expect(early, "tRCD", t0 + P.tRCD)
        self.assertEqual(dev.mem[dev._addr(0, 4, 3)], 0)
        self.assertEqual(dev.bank_row(0), 4)
        payload = bytes((i * 3) & 0xFF for i in range(32))
        write = dev.issue(Write(t0 + P.act_to_cas, 0, 3, payload))
        self.assertTrue(write.accepted, write.violations)
        self.assertEqual(write.data_cycle - write.offered_cycle, P.WL)
        read = dev.issue(Read(t0 + P.act_to_cas + P.word_clocks, 0, 3))
        self.assertTrue(read.accepted, read.violations)
        self.assertEqual(read.data, payload)
        self.assertEqual(read.data_cycle - read.offered_cycle, P.RL)
        self.assertNotEqual(read.offered_cycle, early.offered_cycle)

    def test_byte_mask_on_one_word_and_across_a_burst(self):
        dev, t0 = self.up()
        self.assertTrue(dev.issue(Activate(t0, 0, 7)).accepted)
        wr = t0 + P.act_to_cas
        base = bytes(range(32))
        self.assertTrue(dev.issue(Write(wr, 0, 2, base)).accepted)
        new = bytes((0x80 + i) & 0xFF for i in range(32))
        # Bit 1 leaves the previous byte in place. On a one-WORD burst both
        # mask fields apply to that WORD.
        masked = dev.issue(
            Write(
                wr + 8,
                0,
                2,
                new,
                first_mask=(1 << 0) | (1 << 31),
                last_mask=(1 << 2),
            )
        )
        self.assertTrue(masked.accepted, masked.violations)
        got = dev.issue(Read(wr + 16, 0, 2))
        self.assertTrue(got.accepted, got.violations)
        expect = bytearray(new)
        expect[0] = base[0]
        expect[2] = base[2]
        expect[31] = base[31]
        self.assertEqual(got.data, bytes(expect))

        initial = bytes([0x11]) * 96
        updated = bytes([0x22]) * 96
        burst = wr + 24
        self.assertEqual(P.word_clocks * 3, 24)
        self.assertTrue(dev.issue(Write(burst, 0, 0, initial, burst_count=2)).accepted)
        self.assertTrue(
            dev.issue(
                Write(
                    burst + 24,
                    0,
                    0,
                    updated,
                    burst_count=2,
                    first_mask=1 << 0,
                    last_mask=1 << 1,
                )
            ).accepted
        )
        read = dev.issue(Read(burst + 48, 0, 0, burst_count=2))
        self.assertTrue(read.accepted, read.violations)
        self.assertEqual(len(read.data), 96)
        self.assertEqual(read.data[0], 0x11)
        self.assertEqual(read.data[1], 0x22)
        self.assertEqual(read.data[32:64], bytes([0x22]) * 32)
        self.assertEqual(read.data[64], 0x22)
        self.assertEqual(read.data[65], 0x11)
        self.assertEqual(read.data[66], 0x22)

    def test_row_hit_miss_and_conflict_cycle_counts(self):
        self.assertEqual(P.row_hit_cycles, 12)
        self.assertEqual(P.row_miss_cycles, 28)
        self.assertEqual(P.row_conflict_cycles, 39)
        dev, t0 = self.up()
        self.assertTrue(dev.issue(Activate(t0, 0, 2)).accepted)
        early = dev.issue(Read(t0 + P.tRCD - 1, 0, 0))
        self.expect(early, "tRCD", t0 + P.tRCD)
        miss = dev.issue(Read(t0 + P.act_to_cas, 0, 0))
        self.assertTrue(miss.accepted, miss.violations)
        self.assertEqual(miss.data_cycle - t0, 28)
        self.assertEqual(miss.data_cycle - miss.offered_cycle, 12)
        hit = dev.issue(Read(t0 + P.act_to_cas + P.word_clocks, 0, 1))
        self.assertTrue(hit.accepted, hit.violations)
        self.assertEqual(hit.data_cycle - hit.offered_cycle, P.row_hit_cycles)
        self.assertLess(P.row_hit_cycles, P.row_miss_cycles)

        dev, t0 = self.up()
        self.assertTrue(dev.issue(Activate(t0, 0, 0)).accepted)
        self.assertTrue(dev.issue(Precharge(t0 + P.act_to_pre, 0)).accepted)
        new_act = t0 + P.act_to_pre + P.tRP
        self.assertGreaterEqual(new_act - t0, P.tRC)
        self.assertTrue(dev.issue(Activate(new_act, 0, 1)).accepted)
        payload = bytes([0x5A]) * 32
        write = new_act + P.act_to_cas
        self.assertTrue(dev.issue(Write(write, 0, 0, payload)).accepted)
        self.assertEqual((write + P.WL) - (t0 + P.act_to_pre), P.row_conflict_cycles)
        read = dev.issue(Read(write + P.word_clocks, 0, 0))
        self.assertTrue(read.accepted, read.violations)
        self.assertEqual(read.data, payload)
        self.assertEqual(dev.bank_row(0), 1)

    def test_banks_do_not_alias_and_the_page_wraps(self):
        dev, t0 = self.up()
        for bank in range(4):
            act = dev.issue(Activate(t0 + bank * P.tPPD_ACT, bank, 10 + bank))
            self.assertTrue(act.accepted, act.violations)
        cycle = t0 + 3 * P.tPPD_ACT + P.act_to_cas
        payloads = []
        for bank in range(4):
            payload = bytes((bank * 40 + i) & 0xFF for i in range(32))
            payloads.append(payload)
            wrote = dev.issue(Write(cycle, bank, 0, payload))
            self.assertTrue(wrote.accepted, wrote.violations)
            cycle += P.word_clocks
        for bank in range(4):
            read = dev.issue(Read(cycle, bank, 0))
            self.assertTrue(read.accepted, read.violations)
            self.assertEqual(read.data, payloads[bank])
            cycle += P.word_clocks

        dev, t0 = self.up()
        self.assertTrue(dev.issue(Activate(t0, 0, 5)).accepted)
        first = bytes([0xA0 + (i % 16) for i in range(32)])
        second = bytes([0x40 + (i % 16) for i in range(32)])
        write = t0 + P.act_to_cas
        wrapped = dev.issue(Write(write, 0, 63, first + second, burst_count=1))
        self.assertTrue(wrapped.accepted, wrapped.violations)
        at_63 = dev.issue(Read(write + 16, 0, 63))
        at_0 = dev.issue(Read(write + 24, 0, 0))
        self.assertEqual(at_63.data, first)
        self.assertEqual(at_0.data, second)
        pre = t0 + 64
        self.assertEqual(pre, write + 16 + 8 + P.RL + P.word_clocks + 4)
        closed = dev.issue(Precharge(pre, 0))
        self.assertTrue(closed.accepted, closed.violations)
        self.assertTrue(dev.issue(Activate(pre + P.tRP, 0, 6)).accepted)
        other = dev.issue(Read(pre + P.tRP + P.act_to_cas, 0, 0))
        self.assertEqual(other.data, bytes(32))

    def test_auto_precharge_is_explicit(self):
        for policy in ("open", "closed"):
            dev, t0 = self.up(page_policy=policy)
            self.assertTrue(dev.issue(Activate(t0, 0, 1)).accepted)
            wrote = dev.issue(Write(t0 + P.act_to_cas, 0, 0, bytes([0x5A]) * 32))
            self.assertTrue(wrote.accepted, wrote.violations)
            read = dev.issue(Read(t0 + P.act_to_cas + P.word_clocks, 0, 0))
            self.assertTrue(read.accepted, read.violations)
            self.assertEqual(read.data, bytes([0x5A]) * 32)
            self.assertEqual(dev.bank_row(0), 1)

        dev, t0 = self.up()
        self.assertTrue(dev.issue(Activate(t0, 0, 9)).accepted)
        write = t0 + P.act_to_cas
        payload = bytes([0x77]) * 32
        ap = dev.issue(Write(write, 0, 1, payload, auto_precharge=True))
        self.assertTrue(ap.accepted, ap.violations)
        close_at = write + P.WL + P.word_clocks + P.tWR
        self.assertEqual(close_at, t0 + 48)
        self.assertGreaterEqual(close_at, t0 + P.tRAS)
        self.assertEqual(dev.bank_row(0), 9)
        dev._apply_auto_precharge(close_at - 1)
        self.assertEqual(dev.bank_row(0), 9)
        closed = dev.issue(Read(close_at, 0, 1))
        self.expect(closed, "row_open", None)
        self.assertIsNone(dev.bank_row(0))
        too_soon = dev.issue(Activate(close_at + P.tRP - 1, 0, 9))
        self.expect(too_soon, "tRP", close_at + P.tRP)
        self.assertTrue(dev.issue(Activate(close_at + P.tRP, 0, 9)).accepted)
        again = dev.issue(Read(close_at + P.tRP + P.act_to_cas, 0, 1))
        self.assertEqual(again.data, payload)

    def test_refresh_retains_bytes(self):
        dev, t0 = self.up()
        payload = bytes(range(32))
        self.assertTrue(dev.issue(Activate(t0, 0, 3)).accepted)
        write = t0 + P.act_to_cas
        self.assertTrue(dev.issue(Write(write, 0, 4, payload)).accepted)
        ref = write + P.WL + P.word_clocks + P.tWR
        self.assertEqual(ref, t0 + 48)
        self.assertGreater(ref, t0 + P.tRC)
        early = dev.issue(Refresh(ref - 1))
        self.expect(early, "tWR", ref)
        self.assertEqual(dev.bank_row(0), 3)
        self.assertTrue(dev.issue(Refresh(ref)).accepted)
        self.assertIsNone(dev.bank_row(0))
        act = ref + P.tREFI_FST
        self.assertTrue(dev.issue(Activate(act, 0, 3)).accepted)
        read = dev.issue(Read(act + P.act_to_cas, 0, 4))
        self.assertTrue(read.accepted, read.violations)
        self.assertEqual(read.data, payload)

    def test_reset_keeps_the_array_and_requires_init_again(self):
        dev, t0 = self.up()
        self.assertTrue(dev.issue(Activate(t0, 0, 0)).accepted)
        self.assertTrue(dev.issue(Write(t0 + P.act_to_cas, 0, 0, bytes([0x3C]) * 32)).accepted)
        rst = t0 + P.act_to_cas
        self.assertTrue(dev.issue(Reset(rst)).accepted)
        self.assertEqual(dev.mem[0], 0x3C)
        self.assertIsNone(dev.cl)
        blocked = dev.issue(Activate(rst + P.tRESET - 1, 0, 0))
        self.expect(blocked, "tRESET", rst + P.tRESET)
        pre = rst + P.tRESET
        self.assertTrue(dev.issue(Precharge(pre, all_banks=True)).accepted)
        mrs = pre + P.tRP
        self.assertTrue(dev.issue(ModeRegister(mrs)).accepted)
        act = mrs + P.tMOD
        self.assertTrue(dev.issue(Activate(act, 0, 0)).accepted)
        read = dev.issue(Read(act + P.act_to_cas, 0, 0))
        self.assertEqual(read.data, bytes([0x3C]) * 32)


class TestTimingNegatives(ModelTest):
    def test_active_parallel_command_grid(self):
        dev, t0 = self.up()
        self.assertTrue(dev.issue(Activate(t0, 0, 0)).accepted)
        off_grid = dev.issue(Read(t0 + P.tRCD + 1, 0, 0))
        self.expect(off_grid, "tPPD_grid", t0 + P.act_to_cas)
        self.assertTrue(dev.issue(Read(t0 + P.act_to_cas, 0, 0)).accepted)

    def test_tras_and_trp_boundaries(self):
        dev, t0 = self.up()
        self.assertTrue(dev.issue(Activate(t0, 0, 0)).accepted)
        early = dev.issue(Precharge(t0 + P.tRAS - 1, 0))
        self.expect(early, "tRAS", t0 + P.tRAS)
        self.assertEqual(dev.bank_row(0), 0)
        self.assertTrue(dev.issue(Precharge(t0 + P.act_to_pre, 0)).accepted)
        self.assertIsNone(dev.bank_row(0))
        before_trc = dev.issue(Activate(t0 + P.tRC - 1, 0, 1))
        self.expect(before_trc, "tRC", t0 + P.tRC)
        too_soon = dev.issue(Activate(t0 + P.act_to_pre + P.tRP - 1, 0, 1))
        self.expect(too_soon, "tRP", t0 + P.act_to_pre + P.tRP)
        self.assertIsNone(dev.bank_row(0))
        self.assertTrue(dev.issue(Activate(t0 + P.act_to_pre + P.tRP, 0, 1)).accepted)
        self.assertEqual(dev.bank_row(0), 1)

    def test_trc_to_refresh_while_the_row_is_open(self):
        dev, t0 = self.up()
        self.assertTrue(dev.issue(Activate(t0, 0, 0)).accepted)
        early = dev.issue(Refresh(t0 + P.tRC - 1))
        self.expect(early, "tRC", t0 + P.tRC)
        self.assertFalse(any(v.constraint == "tRP" for v in early.violations))
        self.assertEqual(dev.bank_row(0), 0)
        self.assertTrue(dev.issue(Refresh(t0 + 40)).accepted)
        self.assertIsNone(dev.bank_row(0))

    def test_trrd_and_activate_state_tppd(self):
        dev, t0 = self.up()
        self.assertTrue(dev.issue(Activate(t0, 0, 0)).accepted)
        both = dev.issue(Activate(t0 + P.tRRD - 1, 1, 2))
        self.expect(both, "tRRD", t0 + P.tRRD)
        self.expect(both, "tPPD", t0 + P.tPPD_ACT)
        self.assertTrue(any("activate" in v.detail for v in both.violations if v.constraint == "tPPD"))
        self.assertIsNone(dev.bank_row(1))
        only_ppd = dev.issue(Activate(t0 + P.tRRD, 1, 2))
        self.expect(only_ppd, "tPPD", t0 + P.tPPD_ACT)
        self.assertFalse(any(v.constraint == "tRRD" for v in only_ppd.violations))
        opened = dev.issue(Activate(t0 + P.tPPD_ACT, 1, 2))
        self.assertTrue(opened.accepted, opened.violations)
        self.assertEqual(dev.bank_row(0), 0)
        self.assertEqual(dev.bank_row(1), 2)

    def test_twr_and_programmed_nwr(self):
        dev, t0 = self.up()
        self.assertTrue(dev.issue(Activate(t0, 0, 0)).accepted)
        write = t0 + P.act_to_cas
        self.assertTrue(dev.issue(Write(write, 0, 0, bytes(32))).accepted)
        earliest = write + P.WL + P.word_clocks + P.tWR
        self.assertEqual(earliest, t0 + 48)
        early = dev.issue(Precharge(earliest - 1, 0))
        self.expect(early, "tWR", earliest)
        self.assertFalse(any(v.constraint == "tRAS" for v in early.violations))
        self.assertEqual(dev.bank_row(0), 0)
        self.assertTrue(dev.issue(Precharge(earliest, 0)).accepted)

        dev, t0 = self.up()
        rejected = dev.issue(ModeRegister(t0, nwr=8))
        self.expect(rejected, "nWR", None)
        self.assertEqual(dev.nwr, 12)
        accepted = dev.issue(ModeRegister(t0, nwr=14))
        self.assertTrue(accepted.accepted, accepted.violations)
        act = t0 + P.tMOD
        self.assertTrue(dev.issue(Activate(act, 0, 0)).accepted)
        write = act + P.act_to_cas
        self.assertTrue(dev.issue(Write(write, 0, 0, bytes(32))).accepted)
        base = write + P.WL + P.word_clocks
        early = dev.issue(Precharge(base + P.tWR, 0))
        self.expect(early, "nWR", base + 14)
        self.assertFalse(any(v.constraint == "tWR" for v in early.violations))
        self.assertTrue(dev.issue(Precharge(base + 20, 0)).accepted)

    def test_read_to_precharge_without_trtp(self):
        dev, t0 = self.up()
        self.assertTrue(dev.issue(Activate(t0, 0, 0)).accepted)
        read = t0 + P.act_to_cas
        self.assertTrue(dev.issue(Read(read, 0, 0)).accepted)
        earliest = read + P.RL + P.word_clocks
        self.assertEqual(earliest, t0 + 36)
        self.assertGreater(earliest, t0 + P.tRAS)
        early = dev.issue(Precharge(earliest - 1, 0))
        self.expect(early, "read_to_precharge", earliest)
        self.assertFalse(any(v.constraint == "tRAS" for v in early.violations))
        self.assertEqual(dev.bank_row(0), 0)
        self.assertTrue(dev.issue(Precharge(earliest + 4, 0)).accepted)

    def test_twtr_and_trtw(self):
        dev, t0 = self.up()
        self.assertTrue(dev.issue(Activate(t0, 0, 0)).accepted)
        write = t0 + P.act_to_cas
        payload = bytes([0x42]) * 32
        self.assertTrue(dev.issue(Write(write, 0, 0, payload)).accepted)
        early = dev.issue(Read(write + P.tWTR - 1, 0, 0))
        self.expect(early, "tWTR", write + P.tWTR)
        self.expect(early, "tCCD", write + P.word_clocks)
        self.expect(early, "tPPD", write + P.tPPD_ACT)
        read = dev.issue(Read(write + P.tWTR, 0, 0))
        self.assertTrue(read.accepted, read.violations)
        self.assertEqual(read.data, payload)

        dev, t0 = self.up()
        self.assertTrue(dev.issue(Activate(t0, 0, 0)).accepted)
        read_at = t0 + P.act_to_cas
        self.assertTrue(dev.issue(Read(read_at, 0, 0)).accepted)
        early = dev.issue(Write(read_at + P.tRTW - 1, 0, 0, bytes([0x99]) * 32))
        self.expect(early, "tRTW", read_at + P.tRTW)
        self.assertEqual(dev.mem[0], 0)
        wrote = dev.issue(Write(read_at + P.tRTW, 0, 0, bytes([0x99]) * 32))
        self.assertTrue(wrote.accepted, wrote.violations)
        self.assertEqual(dev.mem[0], 0x99)

    def test_tccd_for_a_multi_word_burst(self):
        dev, t0 = self.up()
        self.assertTrue(dev.issue(Activate(t0, 0, 0)).accepted)
        first = t0 + P.act_to_cas
        self.assertTrue(dev.issue(Read(first, 0, 0, burst_count=1)).accepted)
        early = dev.issue(Read(first + 15, 0, 1))
        self.expect(early, "tCCD", first + 16)
        self.assertFalse(any(v.constraint == "tPPD" for v in early.violations))
        self.assertFalse(any(v.constraint == "tWTR" for v in early.violations))
        self.assertTrue(dev.issue(Read(first + 16, 0, 1)).accepted)

    def test_tmrd_tmod_and_idle_tppd(self):
        dev, t0 = self.up()
        mrs = t0 - P.tMOD
        early = dev.issue(ModeRegister(mrs + P.tMRD - 1, nwr=16))
        self.expect(early, "tMRD", mrs + P.tMRD)
        self.expect(early, "tPPD", mrs + P.tPPD_IDLE)
        self.assertTrue(any("idle" in v.detail for v in early.violations if v.constraint == "tPPD"))
        self.assertEqual(dev.nwr, 12)
        self.assertTrue(dev.issue(ModeRegister(mrs + P.tMRD, nwr=16)).accepted)
        self.assertEqual(dev.nwr, 16)

        dev, t0 = self.up()
        mrs = t0 - P.tMOD
        early = dev.issue(Activate(mrs + P.tMOD - 1, 0, 0))
        self.expect(early, "tMOD", t0)
        self.assertFalse(any(v.constraint == "tPPD" for v in early.violations))
        self.assertTrue(dev.issue(Activate(t0, 0, 0)).accepted)

    def test_refresh_busy_window_is_one_trefi(self):
        dev, t0 = self.up()
        self.assertTrue(dev.issue(Refresh(t0)).accepted)
        self.assertLess(P.tREFI_FST, P.tRFQSd_FST)
        early = dev.issue(Activate(t0 + P.tREFI_FST - 1, 0, 0))
        self.expect(early, "tREFI", t0 + P.tREFI_FST)
        self.assertIsNone(dev.bank_row(0))
        opened = dev.issue(Activate(t0 + P.tREFI_FST, 0, 0))
        self.assertTrue(opened.accepted, opened.violations)
        self.assertEqual(dev.bank_row(0), 0)

        dev, t0 = self.up()
        self.assertTrue(dev.issue(Refresh(t0, refop=1)).accepted)
        early = dev.issue(Activate(t0 + P.tREFI_LP - 1, 0, 1))
        self.expect(early, "tREFI", t0 + P.tREFI_LP)
        self.assertTrue(dev.issue(Activate(t0 + P.tREFI_LP, 0, 1)).accepted)

    def test_loop_refresh_exit(self):
        dev, t0 = self.up(csrfx=1)
        self.assertTrue(dev.issue(Refresh(t0)).accepted)
        early_exit = dev.issue(RefreshExit(t0 + P.tCKSPE - 1))
        self.expect(early_exit, "tCKSPE", t0 + P.tCKSPE)
        busy = dev.issue(Activate(t0 + P.tCKSPE - 1, 0, 0))
        self.expect(busy, "refresh_busy", t0 + P.tCKSPE + P.tCKSPX)
        self.assertTrue(dev.issue(RefreshExit(t0 + P.tCKSPE)).accepted)
        early = dev.issue(Activate(t0 + P.tCKSPE + P.tCKSPX - 1, 0, 0))
        self.expect(early, "tCKSPX", t0 + P.tCKSPE + P.tCKSPX)
        self.assertTrue(dev.issue(Activate(t0 + P.tCKSPE + P.tCKSPX, 0, 0)).accepted)

    def test_zq_windows(self):
        dev, t0 = self.up()
        cursor = t0
        for kind, cycles, name in (
            ("init", P.tZQINIT, "tZQINIT"),
            ("long", P.tZQCL, "tZQCL"),
            ("short", P.tZQCS, "tZQCS"),
            ("reset", P.tZQRESET, "tZQRESET"),
        ):
            self.assertTrue(dev.issue(ZqCal(cursor, kind)).accepted)
            early = dev.issue(Activate(cursor + cycles - 1, 0, 0))
            self.expect(early, name, cursor + cycles)
            cursor = cursor + cycles
        self.assertTrue(dev.issue(Activate(cursor, 0, 0)).accepted)

    def test_init_sequence_order(self):
        dev = RpcDram()
        self.expect(dev.issue(Activate(0, 0, 0)), "init_reset", None)
        self.assertTrue(dev.issue(Reset(0)).accepted)
        self.expect(dev.issue(Activate(P.tRESET - 1, 0, 0)), "tRESET", P.tRESET)
        self.expect(dev.issue(Activate(P.tRESET, 0, 0)), "init_precharge", None)
        self.assertTrue(dev.issue(Precharge(P.tRESET, all_banks=True)).accepted)
        early_mrs = dev.issue(ModeRegister(P.tRESET + P.tRP - 1))
        self.expect(early_mrs, "tRP", P.tRESET + P.tRP)
        self.expect(dev.issue(Activate(P.tRESET + P.tRP, 0, 0)), "init_mrs", None)
        self.assertTrue(dev.issue(ModeRegister(P.tRESET + P.tRP)).accepted)

    def test_remaining_state_constraints(self):
        dev, t0 = self.up()
        self.expect(dev.issue(Activate(t0, 4, 0)), "address", None)
        self.expect(dev.issue(Read(t0, 0, 0)), "row_open", None)
        self.expect(dev.issue(Precharge(t0, 0)), "require_active_bank", None)
        self.expect(dev.issue(Read(t0, 0, 0, burst_count=64)), "burst_count", None)
        self.assertTrue(dev.issue(Activate(t0, 0, 1)).accepted)
        self.expect(dev.issue(Activate(t0 + P.tPPD_ACT, 0, 2)), "require_idle_bank", None)
        self.expect(dev.issue(Read(t0 + P.act_to_cas, 0, 0, row=2)), "row_mismatch", None)
        self.expect(dev.issue(Write(t0 + P.act_to_cas, 0, 0, b"short")), "burst_data", None)
        self.expect(
            dev.issue(Write(t0 + P.act_to_cas, 0, 0, bytes(32), first_mask=-1)),
            "mask",
            None,
        )
        self.expect(dev.issue(ModeRegister(t0 + P.act_to_cas + P.word_clocks, nwr=16)), "require_all_idle", None)

        dev, t0 = self.up()
        self.assertTrue(dev.issue(Activate(t0, 0, 0)).accepted)
        read = t0 + P.act_to_cas
        self.assertTrue(dev.issue(Read(read, 0, 0, auto_precharge=True)).accepted)
        pending = dev.issue(Read(read + P.word_clocks, 0, 1))
        self.expect(pending, "auto_precharge_pending", None)
        self.assertEqual(dev.bank_row(0), 0)

        dev, t0 = self.up()
        self.expect(dev.issue(ModeRegister(t0, cl=10)), "CL", None)
        self.assertEqual(dev.cl, 11)
        self.expect(dev.issue(ModeRegister(t0, csrfx=2)), "CSRFX", None)
        self.expect(dev.issue(ModeRegister(t0, refop=2)), "REFOP", None)
        self.expect(dev.issue(Refresh(t0, refop=2)), "REFOP", None)
        self.assertTrue(dev.issue(ModeRegister(t0, zout=0)).accepted)
        self.assertTrue(dev.issue(Activate(t0 + P.tMOD, 0, 0)).accepted)
        self.expect(dev.issue(Read(t0 + P.tMOD + P.act_to_cas, 0, 0)), "zout", None)
        self.assertTrue(
            dev.issue(Write(t0 + P.tMOD + P.act_to_cas, 0, 0, bytes([7]) * 32)).accepted
        )
        self.assertEqual(dev.mem[0], 7)

        dev, t0 = self.up()
        self.expect(dev.issue(RefreshExit(t0)), "refresh_mode", None)
        self.expect(dev.issue(ZqCal(t0, "nope")), "zq_kind", None)
        self.expect(dev.issue(Command("nope", t0)), "opcode", None)
        self.assertTrue(dev.issue(Activate(t0, 0, 0)).accepted)
        self.expect(dev.issue(Activate(t0 - 1, 1, 0)), "monotonic", t0)

        fresh = RpcDram()
        self.expect(fresh.issue(Reset(-1)), "cycle", 0)
        self.assertEqual(fresh.phase, "powerup")


if __name__ == "__main__":
    unittest.main()
