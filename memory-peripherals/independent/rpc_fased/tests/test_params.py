"""Catalog checks: every timing has a citation, and cycle counts use ceil."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rpc_fased.params import ADOPTED, ALL_PARAMS, GEOMETRY, P, cycles_from_ps


class TestCatalog(unittest.TestCase):
    def test_headline_speed_grade(self):
        self.assertEqual(P.tCK_ns, 1.25)
        self.assertEqual(P.fCK_MHz, 800)
        self.assertEqual(P.CL, 11)
        self.assertEqual(P.AL, 1)
        self.assertEqual(P.RL, 12)
        self.assertEqual(P.WL, 12)
        self.assertEqual(P.tRCD, 11)
        self.assertEqual(P.tRP, 11)
        self.assertEqual(P.tRAS, 28)
        self.assertEqual(P.tRC, 39)
        self.assertEqual(P.tRRD, 6)
        self.assertEqual(P.tWR, 12)
        self.assertEqual(P.nWR_MIN, 12)
        self.assertEqual(P.BL_BEATS, 16)
        self.assertEqual(P.word_clocks, 8)
        self.assertEqual(P.tREF_BUSY_FST, 80)
        self.assertEqual(P.tREFI_LP, 2560)
        self.assertEqual(P.row_hit_cycles, 12)
        self.assertEqual(P.act_to_cas, 16)
        self.assertEqual(P.act_to_pre, 32)
        self.assertEqual(P.row_miss_cycles, 28)
        self.assertEqual(P.row_conflict_cycles, 39)
        self.assertEqual(ADOPTED["refresh_duration"], 80)
        self.assertEqual(P.tRAS + P.tRP, P.tRC)
        self.assertEqual(P.act_to_cas + P.RL, P.row_miss_cycles)

    def test_ceil_examples(self):
        self.assertEqual(cycles_from_ps(13_750), 11)  # exact
        self.assertEqual(cycles_from_ps(7_000), 6)  # 5.6 -> 6
        self.assertEqual(cycles_from_ps(1_750), 2)  # 1.4 -> 2
        self.assertEqual(cycles_from_ps(2_000), 2)  # 1.6 -> 2
        self.assertEqual(cycles_from_ps(12_000), 10)  # 9.6 -> 10
        self.assertEqual(P.tMOD, 12)
        self.assertEqual(P.tCKE, 6)

    def test_every_param_is_cited(self):
        names = [item.name for item in ALL_PARAMS]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("tRCD", names)
        self.assertIn("tREFI_FST", names)
        self.assertIn("RL", names)
        for item in ALL_PARAMS:
            self.assertIn(item.source, ("specified", "inferred"))
            self.assertTrue(item.section)
            self.assertGreaterEqual(item.page, 1)
            self.assertLessEqual(item.page, 74)
            self.assertTrue(item.unit)
            if item.picoseconds is not None:
                self.assertEqual(item.cycles, cycles_from_ps(item.picoseconds))

    def test_geometry_is_256mbit(self):
        bits = (
            GEOMETRY.banks
            * GEOMETRY.rows
            * GEOMETRY.columns
            * GEOMETRY.word_bytes
            * 8
        )
        self.assertEqual(bits, 256 * 1024 * 1024)
        self.assertEqual(GEOMETRY.columns * GEOMETRY.word_bytes, GEOMETRY.page_bytes)


if __name__ == "__main__":
    unittest.main()
