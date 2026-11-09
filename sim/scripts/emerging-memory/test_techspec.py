#!/usr/bin/env python3
"""Directed checks for the technology-spec timing reference."""

import unittest

from techspec import (
    Access,
    TechSpecModel,
    issuer_occupancy,
    overlapping_services,
    retention_index,
    transfer_bytes,
)


def run_model(model, offers):
    """offers maps cycle -> (ar, aw, w_last). Missing cycles are idle."""
    if not offers:
        return []
    last = max(offers)
    out = []
    while model.t_cycle <= last or model.has_inflight():
        ar, aw, w_last = offers.get(model.t_cycle, (None, None, False))
        out.append(model.step(ar=ar, aw=aw, w_last=w_last))
        if model.t_cycle > last + 100000:
            raise AssertionError("model did not drain")
    return out


class TechSpecTests(unittest.TestCase):
    def test_single_beat_release_matches_latency_pipe_formula(self):
        model = TechSpecModel(read_latency=1, write_latency=1, read_max=4, write_max=4)
        result = model.step(ar=Access(addr=0x1000, length=0, size=3))
        self.assertEqual(result["accepted_read"]["start"], 0)
        self.assertEqual(result["accepted_read"]["occupancy"], 1)
        self.assertEqual(result["accepted_read"]["release"], 0)
        self.assertIs(result["completed_read"], result["accepted_read"])
        self.assertEqual(model.pending_reads, 0)
        self.assertEqual(model.device_read_bytes, 8)

    def test_latency_thirty_presents_at_start_plus_29(self):
        model = TechSpecModel(read_latency=30, read_service_cycles=1)
        first = model.step(ar=Access(addr=0x40, length=0, size=0))
        self.assertIsNone(first["completed_read"])
        self.assertEqual(first["accepted_read"]["release"], 29)
        model.advance_to(29)
        done = model.step()
        self.assertEqual(done["t_cycle"], 29)
        self.assertEqual(done["completed_read"]["addr"], 0x40)
        self.assertEqual(transfer_bytes(0, 0), 1)

    def test_burst_occupancy_is_max_of_service_and_beats(self):
        self.assertEqual(issuer_occupancy(1, 3), 4)
        self.assertEqual(issuer_occupancy(20, 3), 20)
        model = TechSpecModel(read_latency=2, read_service_cycles=1, read_max=4)
        model.step(ar=Access(addr=0, length=3, size=3))
        second = model.step(ar=Access(addr=32, length=3, size=3))
        self.assertEqual(model.schedule[0]["start"], 0)
        self.assertEqual(model.schedule[0]["occupancy"], 4)
        self.assertEqual(second["accepted_read"]["start"], 4)
        self.assertEqual(second["accepted_read"]["release"], 5)
        self.assertEqual(model.device_read_bytes, 64)

    def test_same_cycle_read_is_ordered_before_write(self):
        model = TechSpecModel(
            read_latency=5, write_latency=5, read_service_cycles=4, write_service_cycles=4
        )
        result = model.step(
            ar=Access(addr=0x10, length=0, size=3),
            aw=Access(addr=0x20, length=0, size=3),
            w_last=True,
        )
        self.assertEqual(result["accepted_read"]["start"], 0)
        self.assertEqual(result["accepted_write"]["start"], 4)
        self.assertEqual(model.next_service, 8)
        self.assertEqual(overlapping_services(model.schedule), [])

    def test_write_address_can_precede_last_data_beat(self):
        model = TechSpecModel(write_latency=3, write_service_cycles=1)
        first = model.step(aw=Access(addr=0x80, axi_id=2, length=0, size=3))
        self.assertIsNone(first["accepted_write"])
        self.assertEqual(model.pending_aw, 1)
        second = model.step(w_last=True)
        self.assertEqual(second["accepted_write"]["addr"], 0x80)
        self.assertEqual(second["accepted_write"]["id"], 2)
        self.assertEqual(second["accepted_write"]["start"], 1)
        self.assertEqual(model.logical_write_bytes, model.device_write_bytes)

    def test_outstanding_cap_blocks_until_the_cycle_after_completion(self):
        model = TechSpecModel(read_latency=10, read_service_cycles=1, read_max=1)
        self.assertTrue(model.step(ar=Access(0, length=0, size=3))["ar_ready"])
        blocked = model.step(ar=Access(8, length=0, size=3))
        self.assertFalse(blocked["ar_ready"])
        self.assertIsNone(blocked["accepted_read"])
        # Release is cycle 9. The counter still reads full during that cycle.
        model.advance_to(9)
        completing = model.step(ar=Access(8, length=0, size=3))
        self.assertEqual(completing["t_cycle"], 9)
        self.assertFalse(completing["ar_ready"])
        self.assertIsNotNone(completing["completed_read"])
        self.assertIsNone(completing["accepted_read"])
        opened = model.step(ar=Access(8, length=0, size=3))
        self.assertTrue(opened["ar_ready"])
        self.assertEqual(opened["accepted_read"]["addr"], 8)
        self.assertEqual(opened["accepted_read"]["start"], 10)

    def test_response_backpressure_holds_the_head(self):
        model = TechSpecModel(read_latency=2, read_service_cycles=1, read_max=2)
        admitted = model.step(ar=Access(0, length=0, size=3))
        self.assertEqual(admitted["accepted_read"]["release"], 1)
        self.assertIsNone(admitted["completed_read"])
        held = model.step(r_sink_ready=False)
        self.assertEqual(held["t_cycle"], 1)
        self.assertIsNone(held["completed_read"])
        self.assertEqual(model.pending_reads, 1)
        released = model.step()
        self.assertEqual(released["completed_read"]["addr"], 0)

    def test_endurance_flag_does_not_change_release_time(self):
        def once(limit):
            model = TechSpecModel(
                write_latency=6, write_service_cycles=1, endurance_limit_bytes=limit
            )
            model.step(aw=Access(0, length=0, size=3), w_last=True)
            model.step(aw=Access(8, length=0, size=3), w_last=True)
            return [(e["release"], e["start"]) for e in model.schedule], model.endurance_exceeded

        unlimited, flag_off = once(0)
        limited, flag_on = once(8)
        self.assertEqual(unlimited, limited)
        self.assertFalse(flag_off)
        self.assertTrue(flag_on)
        self.assertEqual(unlimited[1][0], 6)

    def test_retention_classifies_hits_and_does_not_treat_a_miss_as_stale(self):
        model = TechSpecModel(read_latency=1, write_latency=1, retention_cycles=4, retention_sets=4)
        model.step(aw=Access(0x000, length=0, size=3), w_last=True)
        model.advance_to(5)
        model.step(ar=Access(0x000, length=0, size=3))
        self.assertEqual(model.retention_stale_reads, 1)
        self.assertEqual(model.retention_fresh_reads, 0)
        # Same set, different tag: the first line is evicted. The later read is unknown.
        model.step(aw=Access(0x100, length=0, size=3), w_last=True)
        model.step(ar=Access(0x000, length=0, size=3))
        self.assertEqual(model.retention_unknown_reads, 1)
        self.assertEqual(model.retention_stale_reads, 1)
        fresh = TechSpecModel(read_latency=1, write_latency=1, retention_cycles=5, retention_sets=4)
        fresh.step(aw=Access(0, length=0, size=3), w_last=True)
        fresh.advance_to(5)
        fresh.step(ar=Access(0, length=0, size=3))
        self.assertEqual(fresh.retention_fresh_reads, 1)
        disabled = TechSpecModel(retention_cycles=0, retention_sets=4)
        disabled.step(ar=Access(0, length=0, size=3))
        self.assertEqual(disabled.retention_unknown_reads, 0)

    def test_retention_index_uses_the_line_above_the_granule(self):
        self.assertEqual(retention_index(0x3F, 64, 64), retention_index(0x00, 64, 64))
        self.assertNotEqual(retention_index(0x40, 64, 64)[0], retention_index(0x00, 64, 64)[0])

    def test_illegal_schedule_is_detected(self):
        illegal = [
            {"start": 0, "occupancy": 4},
            {"start": 2, "occupancy": 4},
        ]
        self.assertEqual(len(overlapping_services(illegal)), 1)
        legal = [
            {"start": 0, "occupancy": 4},
            {"start": 4, "occupancy": 4},
        ]
        self.assertEqual(overlapping_services(legal), [])

    def test_advance_to_matches_cycle_stepping(self):
        def drive(fast):
            model = TechSpecModel(read_latency=6, write_latency=3, read_service_cycles=3, read_max=4)
            offers = {
                0: (Access(0, length=3, size=3), None, False),
                2: (Access(32, length=0, size=3), Access(64, length=0, size=3), True),
                20: (Access(96, length=0, size=3), None, False),
            }
            if not fast:
                return run_model(model, offers), model
            cursor = 0
            results = []
            for cycle in sorted(offers):
                model.advance_to(cycle)
                ar, aw, w_last = offers[cycle]
                results.append(model.step(ar=ar, aw=aw, w_last=w_last))
                cursor = cycle
            model.advance_to(cursor + 50)
            while model.has_inflight():
                results.append(model.step())
            return results, model

        slow_results, slow = drive(False)
        fast_results, fast = drive(True)
        self.assertEqual(slow.schedule, fast.schedule)
        self.assertEqual(slow.issuer_busy_cycles, fast.issuer_busy_cycles)
        self.assertEqual(slow.device_read_bytes, fast.device_read_bytes)
        self.assertEqual(slow.device_write_bytes, fast.device_write_bytes)
        self.assertEqual(overlapping_services(slow.schedule), [])
        self.assertGreater(len(slow_results), len(fast_results))

    def test_repeated_runs_match(self):
        def once():
            model = TechSpecModel(read_latency=8, write_latency=12, read_max=2, write_max=2)
            run_model(
                model,
                {
                    0: (Access(0, length=3, size=3), None, False),
                    1: (None, Access(128, length=1, size=2), True),
                    2: (Access(256, length=0, size=3), None, False),
                    3: (Access(512, length=0, size=3), None, False),
                },
            )
            return (
                model.schedule,
                model.issuer_busy_cycles,
                model.endurance_exceeded,
                model.t_cycle,
            )

        self.assertEqual(once(), once())


if __name__ == "__main__":
    unittest.main()
