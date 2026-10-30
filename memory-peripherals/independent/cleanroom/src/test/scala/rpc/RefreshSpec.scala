package rpc

import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec

import Constraint._

class RefreshSpec extends AnyFlatSpec with ChiselScalatestTester {
  behavior of "refresh (section 5, Tables 7-5 and 11-3)"

  // tCK 1250 ps, one bank, one-shot FST: reading 1 ends at REF + 327924,
  // reading 2 at REF + 400244 (RpcConfigSpec checks the arithmetic).
  private val fst1 = 327924L
  private val fst2 = 400244L

  private def withRef(rs: Int)(body: (Bench, Long) => Unit): Unit =
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250, refreshSelect = rs)
      val r = b.init()
      b.accept(r, Packet.ref(0x1))
      body(b, r)
    }

  it should "report an INTERPRETATION under refreshSelect 0 while the readings disagree" in {
    withRef(0) { (b, r) =>
      val res = b.interpretation(r + fst1, Packet.act(1, 0), REFRESH_BUSY, r + fst2)
      assert(res.e1 == r + fst1 && res.e2 == r + fst2)
    }
  }

  it should "report a VIOLATION under refreshSelect 0 when early under every reading" in {
    withRef(0) { (b, r) =>
      b.violation(r + fst1 - 1, Packet.act(1, 0), REFRESH_BUSY, r + fst1)
      b.violation(r + 4, Packet.act(1, 0), REFRESH_BUSY, r + fst1)
    }
  }

  it should "accept once both readings have completed under refreshSelect 0" in {
    withRef(0) { (b, r) =>
      b.accept(r + fst2, Packet.act(1, 0))
    }
  }

  it should "collapse to the rows x tREFI reading under refreshSelect 1" in {
    withRef(1) { (b, r) =>
      b.boundary(r + fst1, Packet.act(1, 0), REFRESH_BUSY)
    }
  }

  it should "collapse to the 64 ms reading under refreshSelect 2" in {
    withRef(2) { (b, r) =>
      b.violation(r + fst1, Packet.act(1, 0), REFRESH_BUSY, r + fst2)
      b.boundary(r + fst2, Packet.act(1, 0), REFRESH_BUSY)
    }
  }

  it should "apply a command after an INTERPRETATION as if refresh had finished" in {
    withRef(0) { (b, r) =>
      val t = r + fst1 + 5
      b.interpretation(t, Packet.act(1, 0), REFRESH_BUSY, r + fst2)
      // the ACT was applied: bank 1 is open and tRCD runs from t
      b.violation(t + 8, Packet.rd(1, 0), TRCD, t + 16)
      b.accept(t + 16, Packet.rd(1, 0))
    }
  }

  it should "scale with bank count, REFOP and CSRFX" in {
    val cases = Seq(
      // (banks mask, refop, csrfx, rs1 offset, rs2 offset)
      (0x1, 0, 1, 327934L, 400254L),
      (0xf, 1, 0, 41950724L, 51207684L)
    )
    for ((mask, refop, csrfx, o1, o2) <- cases) {
      test(new RpcTimingChecker) { dut =>
        val b = new Bench(dut, 1250, refreshSelect = 0)
        val r = b.init(csrfx = csrfx)
        b.accept(r, Packet.ref(mask, refop))
        b.violation(r + o1 - 1, Packet.act(0, 0), REFRESH_BUSY, r + o1)
        b.interpretation(r + o1, Packet.act(0, 0), REFRESH_BUSY, r + o2)
      }
    }
  }

  it should "convert refresh time at another clock period (tCK 2500 ps)" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 2500, refreshSelect = 0)
      val r = b.init()
      b.accept(r, Packet.ref(0x2))
      b.violation(r + 163961, Packet.zq(2), REFRESH_BUSY, r + 163962)
      b.interpretation(r + 163962, Packet.zq(2), REFRESH_BUSY, r + 200122)
    }
  }

  it should "convert the one-shot FST single-bank bound at every tCK(avg) row" in {
    val offsets = Seq(1250 -> (327924L, 400244L), 1500 -> (273270L, 333537L), 1667 -> (245894L, 300123L),
      2500 -> (163962L, 200122L), 4000 -> (102477L, 125077L))
    for ((tck, (o1, o2)) <- offsets) {
      assert(RpcConfig.derived(tck).refreshCycles(1, 1, lp = false, loop = false) == o1)
      assert(RpcConfig.derived(tck).refreshCycles(2, 1, lp = false, loop = false) == o2)
      test(new RpcTimingChecker) { dut =>
        val b = new Bench(dut, tck, refreshSelect = 0)
        val r = b.init()
        b.accept(r, Packet.ref(0x8))
        b.violation(r + o1 - 1, Packet.act(3, 0), REFRESH_BUSY, r + o1)
        b.interpretation(r + o1, Packet.act(3, 0), REFRESH_BUSY, r + o2)
      }
    }
  }

  it should "reject a reserved REFOP and an empty bank mask" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val r = b.init()
      b.violation(r, Packet.ref(0x1, 2), REF_REFOP_RESERVED, 0)
      b.violation(r, Packet.ref(0x0), PKT_NO_BANK, 0)
      b.accept(r, Packet.ref(0x1))
    }
  }
}
