"""Pin-trace checks and the 200 MHz profile. Not part of the 24 isolated tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from rpc_fased.check import parse_pin_log, replay, shift_first_column
from rpc_fased.device import Activate, Precharge, Read, Refresh, RpcDram, Write
from rpc_fased.packets import decode_packet
from rpc_fased.params import P
from rpc_fased.profiles import matches_speed_1600, profile_for

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "results" / "logs"


class ProfileTests(unittest.TestCase):
    def test_1600_profile_matches_the_isolated_column(self) -> None:
        prof = profile_for(1250, cl=11)
        self.assertTrue(matches_speed_1600(prof))

    def test_200_mhz_uses_nanosecond_ceil_and_keeps_tck_counts(self) -> None:
        prof = profile_for(5000)
        self.assertEqual(prof.CL, 3)
        self.assertEqual(prof.tRCD, 3)
        self.assertEqual(prof.tRP, 3)
        self.assertEqual(prof.tRAS, 7)
        self.assertEqual(prof.tRC, 10)
        self.assertEqual(prof.tRRD, 2)
        self.assertEqual(prof.tWR, 3)
        self.assertEqual(prof.tPPD_ACT, 8)
        self.assertEqual(prof.tRESET, 1000)
        self.assertEqual(prof.tZQINIT, 400)
        self.assertEqual(prof.tREF_BUSY_FST, 20)
        self.assertEqual(prof.RL, 4)
        self.assertIn(8, prof.allowed_cl)


class PacketTests(unittest.TestCase):
    def test_init_and_column_packets_from_the_datasheet_fields(self) -> None:
        self.assertEqual(decode_packet(0x00000001, 10).kind, "reset")
        pre = decode_packet(0x03C40000, 20)
        self.assertEqual((pre.kind, pre.all_banks), ("precharge", True))
        mrs = decode_packet(0x04020000, 30)
        self.assertEqual((mrs.kind, mrs.cl, mrs.nwr, mrs.zout), ("mrs", 8, 4, 2))
        zq = decode_packet(0x00010001, 40)
        self.assertEqual((zq.kind, zq.zq), ("zq", "init"))
        act = decode_packet(0x00050000, 50)
        self.assertEqual((act.kind, act.bank, act.row), ("activate", 0, 0))
        write = decode_packet(0x00012000, 60)
        self.assertEqual((write.kind, write.column, write.burst_count), ("write", 8, 0))


class ReplayTests(unittest.TestCase):
    def test_standalone_pin_log_meets_the_200_mhz_minima(self) -> None:
        observed = parse_pin_log((LOGS / "eth_full_pin_run.log").read_text())
        self.assertGreaterEqual(len(observed), 21)
        _device, reports, counts = replay(observed, profile_for(5000, cl=8))
        self.assertEqual(reports, [], [item.format() for item in reports])
        self.assertEqual(counts["activate"], 6)
        self.assertEqual((counts["read"], counts["write"]), (3, 3))

    def test_rocket_and_boom_traces_have_no_violations_and_cover_four_banks(self) -> None:
        prof = profile_for(5000, cl=8)
        for name, acts in (
            ("chipyard_eth_rocket_stdout.log", 130),
            ("chipyard_eth_boom_stdout.log", 135),
        ):
            observed = parse_pin_log((LOGS / name).read_text(errors="replace"))
            _device, reports, counts = replay(observed, prof)
            self.assertEqual(reports, [], [item.format() for item in reports[:8]])
            self.assertEqual(counts["activate"], acts)
            self.assertNotIn("refresh", counts)
            banks = {item.command.bank for item in observed if item.command.kind == "activate"}
            self.assertEqual(banks, {0, 1, 2, 3})

    def test_moved_column_is_reported_and_not_accepted(self) -> None:
        observed = parse_pin_log((LOGS / "eth_full_pin_run.log").read_text())
        prof = profile_for(5000, cl=8)
        shifted = shift_first_column(observed, prof.tRCD)
        _device, reports, _counts = replay(shifted, prof)
        self.assertTrue(any(item.constraint == "tRCD" for item in reports), reports)
        column = next(item for item in reports if item.constraint == "tRCD")
        self.assertEqual(column.earliest_legal_cycle, column.offered_cycle + 1)
        self.assertIn("activate@", column.previous)

    def test_direct_early_commands_name_the_constraint(self) -> None:
        prof = profile_for(5000, cl=8)
        dev = RpcDram(timing=prof)
        ready = dev.initialize(nwr=prof.nWR_MIN, cl=8, zout=2)
        act = ready
        self.assertTrue(dev.issue(Activate(act, 0, 1)).accepted)
        early = dev.issue(Read(act + prof.tRCD - 1, 0, 0))
        self.assertFalse(early.accepted)
        self.assertEqual(
            {item.constraint for item in early.violations},
            {"tPPD", "tRCD"},
        )
        legal = act + max(prof.tRCD, prof.tPPD_ACT)
        self.assertTrue(dev.issue(Read(legal, 0, 0)).accepted)
        early_pre = dev.issue(Precharge(legal + 1, 0))
        self.assertFalse(early_pre.accepted)
        self.assertIn(
            early_pre.violations[0].constraint,
            {"tRAS", "read_to_precharge", "tPPD"},
        )

    def test_trace_injections_are_named_and_not_delayed(self) -> None:
        observed = parse_pin_log((LOGS / "eth_full_pin_run.log").read_text())
        prof = profile_for(5000, cl=8)
        act = next(item for item in observed if item.command.kind == "activate")
        index = observed.index(act)
        early_pre = Precharge(act.cycle + prof.tRAS - 1, act.command.bank)
        self.assertLess(early_pre.cycle, observed[index + 1].cycle)
        with_pre = (
            observed[: index + 1]
            + [type(act)(early_pre.cycle, 0, early_pre)]
            + observed[index + 1 :]
        )
        _device, reports, _counts = replay(with_pre, prof)
        tras = next(item for item in reports if item.constraint == "tRAS")
        self.assertEqual(tras.earliest_legal_cycle, act.cycle + prof.tRAS)
        self.assertLess(tras.offered_cycle, tras.earliest_legal_cycle)

        read = next(item for item in observed if item.command.kind == "read")
        rindex = observed.index(read)
        early_write = Write(
            read.cycle + prof.tRTW - 1,
            read.command.bank,
            read.command.column,
            bytes(32),
        )
        self.assertLess(early_write.cycle, observed[rindex + 1].cycle)
        with_write = (
            observed[: rindex + 1]
            + [type(read)(early_write.cycle, 0, early_write)]
            + observed[rindex + 1 :]
        )
        _device, reports, _counts = replay(with_write, prof)
        self.assertTrue(any(item.constraint == "tRTW" for item in reports))

        last = next(item for item in reversed(observed) if item.command.kind == "read")
        clocks = (last.command.burst_count + 1) * prof.word_clocks
        data_end = last.cycle + prof.RL + clocks
        ref_at = last.cycle + ((data_end - last.cycle + prof.tPPD_ACT - 1) // prof.tPPD_ACT) * prof.tPPD_ACT
        refreshed = observed + [
            type(last)(ref_at, 0, Refresh(ref_at, (0, 1, 2, 3), refop=0)),
            type(last)(ref_at + 1, 0, Activate(ref_at + 1, 0, 0)),
        ]
        _device, reports, _counts = replay(refreshed, prof)
        busy = next(item for item in reports if item.constraint == "tREFI")
        self.assertEqual(busy.earliest_legal_cycle, ref_at + prof.tREF_BUSY_FST)
        self.assertEqual(busy.offered_cycle, ref_at + 1)


class OriginalComparison(unittest.TestCase):
    def test_refresh_interpretation_disagrees_with_the_row_step_formula(self) -> None:
        # The original Python model stalls for every row of every selected
        # bank. The isolated model stalls for one tREFI. Both cite Section 5;
        # the datasheet does not give tRFC.
        self.assertEqual(P.tREF_BUSY_FST, 80)
        self.assertEqual(4096 * 80 * 4, 1_310_720)


if __name__ == "__main__":
    unittest.main()
