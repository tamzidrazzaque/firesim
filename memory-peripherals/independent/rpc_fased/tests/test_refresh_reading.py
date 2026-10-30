"""Section 5 refresh readings. The default device stays on one tREFI."""

from __future__ import annotations

import unittest

from rpc_fased.device import Activate, ModeRegister, Refresh, RefreshExit, RpcDram
from rpc_fased.params import GEOMETRY, P
from rpc_fased.profiles import profile_for
from rpc_fased.refresh import (
    lp_bank_limit_matches_hot_retention,
    one_trefi_cycles,
    row_step_cycles,
    row_step_ns,
)


class RefreshReading(unittest.TestCase):
    def test_products(self) -> None:
        self.assertEqual(one_trefi_cycles(P.tREFI_FST), 80)
        self.assertEqual(row_step_cycles(P.tREFI_FST, 1), 4096 * 80)
        self.assertEqual(row_step_cycles(P.tREFI_FST, 2), 4096 * 80 * 2)
        self.assertEqual(row_step_cycles(P.tREFI_FST, 4), 1_310_720)
        self.assertEqual(row_step_ns(100, 4) / 1e6, 1.6384)
        self.assertAlmostEqual(row_step_ns(3200, 4) / 1e6, 52.4288, places=3)
        hot = lp_bank_limit_matches_hot_retention()
        self.assertEqual(hot, {1: True, 2: True, 3: False, 4: False})

    def test_one_trefi_still_rejects_only_inside_one_period(self) -> None:
        dev = RpcDram(refresh_occupancy="one_trefi")
        t0 = dev.initialize()
        ref = dev.issue(Refresh(t0, banks=(0,)))
        self.assertTrue(ref.accepted)
        early = dev.issue(Activate(t0 + P.tREFI_FST - 1, 0, 0))
        self.assertFalse(early.accepted)
        self.assertEqual(early.violations[0].constraint, "tREFI")
        self.assertTrue(dev.issue(Activate(t0 + P.tREFI_FST, 0, 0)).accepted)

    def test_row_step_scales_with_the_bank_mask(self) -> None:
        for banks in ((0,), (0, 1), (0, 1, 2, 3)):
            dev = RpcDram(refresh_occupancy="row_step")
            t0 = dev.initialize()
            self.assertTrue(dev.issue(Refresh(t0, banks=banks)).accepted)
            window = GEOMETRY.rows * P.tREFI_FST * len(banks)
            early = dev.issue(Activate(t0 + window - 1, 0, 0))
            self.assertFalse(early.accepted)
            self.assertEqual(early.violations[0].earliest_legal_cycle, t0 + window)
            self.assertEqual(early.violations[0].offered_cycle, t0 + window - 1)
            self.assertTrue(dev.issue(Activate(t0 + window, 0, 1)).accepted)

    def test_row_step_at_200_mhz_and_a_command_during_refresh(self) -> None:
        prof = profile_for(5000, cl=8)
        dev = RpcDram(timing=prof, refresh_occupancy="row_step")
        t0 = dev.initialize(cl=8, nwr=prof.nWR_MIN, zout=2)
        self.assertTrue(dev.issue(Refresh(t0, banks=(0, 1, 2, 3))).accepted)
        window = 4096 * prof.tREF_BUSY_FST * 4
        self.assertEqual(window, 327_680)
        mid = dev.issue(Activate(t0 + 20, 0, 0))
        self.assertFalse(mid.accepted)
        self.assertEqual(mid.violations[0].constraint, "tREFI")
        self.assertTrue(dev.issue(Activate(t0 + window, 0, 0)).accepted)

    def test_loop_exit_tail_is_optional(self) -> None:
        dev = RpcDram(loop_finish="row_step")
        t0 = dev.initialize(csrfx=1)
        self.assertTrue(dev.issue(Refresh(t0, banks=(0, 1))).accepted)
        exit_at = t0 + P.tCKSPE
        self.assertTrue(dev.issue(RefreshExit(exit_at)).accepted)
        tail = GEOMETRY.rows * P.tREFI_FST * 2
        early = dev.issue(Activate(exit_at + P.tCKSPX + tail - 1, 0, 0))
        self.assertFalse(early.accepted)
        self.assertEqual(early.violations[0].constraint, "tREFI")
        legal = dev.issue(Activate(exit_at + P.tCKSPX + tail, 0, 0))
        self.assertTrue(legal.accepted)
        plain = RpcDram()
        u0 = plain.initialize(csrfx=1)
        self.assertTrue(plain.issue(Refresh(u0)).accepted)
        self.assertTrue(plain.issue(RefreshExit(u0 + P.tCKSPE)).accepted)
        later = plain.issue(Activate(u0 + P.tCKSPE + P.tCKSPX, 0, 0))
        self.assertTrue(later.accepted, later.violations)


if __name__ == "__main__":
    unittest.main()
