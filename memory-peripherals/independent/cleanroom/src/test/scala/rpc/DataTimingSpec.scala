package rpc

import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec

import Constraint._

class DataTimingSpec extends AnyFlatSpec with ChiselScalatestTester {
  behavior of "burst data timing (sections 2.5, 2.6, 3.3, 3.10, Figures 12-2, 12-3, 12-6, 12-11)"

  // tCK 1250 ps, CL = 11: RL = WL = 12. A burst of n WORDs ends at cmd + 12 + 8n;
  // the next packet needs STB low tBESL after that plus the 2-cycle STB lead.

  it should "hold the bus after a read burst for tBESL(read) + STB lead" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.accept(a, Packet.act(0, 1))
      val r = a + 16
      b.accept(r, Packet.rd(0, 3, words = 1))
      // bus free at r + 12 + 8 + 9 + 2 = r + 31, next grid slot r + 32
      b.violation(r + 24, Packet.pre(1), TBESL_READ, r + 32)
      b.violation(r + 31, Packet.pre(1), TPPD_ACTIVE, r + 32)
      b.accept(r + 32, Packet.pre(1))
    }
  }

  it should "scale the read window with the burst count" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.accept(a, Packet.act(0, 1))
      val r = a + 16
      b.accept(r, Packet.rd(0, 0, words = 4))
      // r + 12 + 32 + 11 = r + 55 -> r + 56
      b.violation(r + 48, Packet.rd(0, 4, words = 1), TBESL_READ, r + 56)
      b.accept(r + 56, Packet.rd(0, 4, words = 1))
      // 64 WORDs: r2 + 12 + 512 + 11 = r2 + 535 -> r2 + 536
      val r2 = r + 56
      b.accept(r2 + 32, Packet.rd(0, 0, words = 64))
      val r3 = r2 + 32
      b.violation(r3 + 528, Packet.pre(1), TBESL_READ, r3 + 536)
      b.accept(r3 + 536, Packet.pre(1))
    }
  }

  it should "hold the bus after a write burst for tBESL(write) + STB lead" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.accept(a, Packet.act(2, 1))
      val w = a + 16
      b.accept(w, Packet.wr(2, 0, words = 1))
      // bus free at w + 12 + 8 + 11 + 2 = w + 33 -> w + 40; tWR (12) ends at w + 32
      b.violation(w + 32, Packet.pre(4), TBESL_WRITE, w + 40)
      b.violation(w + 39, Packet.pre(4), TPPD_ACTIVE, w + 40)
      b.accept(w + 40, Packet.pre(4))
    }
  }

  it should "take RL from the CL programmed by MRS (tCK 4000 ps)" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 4000)
      val a = b.init(cl = 3)
      assert(b.decodeOnly(Packet.rd(0, 0)).latency == 4)
      b.accept(a, Packet.act(0, 1))
      val r = a + 8
      b.accept(r, Packet.rd(0, 0))
      // CL = 3: r + 4 + 8 + 11 = r + 23 -> r + 24
      b.violation(r + 16, Packet.rd(0, 1), TBESL_READ, r + 24)
      b.accept(r + 24, Packet.rd(0, 1))
      // Reprogram CL = 8 while the bank stays open (Table 8-3: MRS after READ is legal).
      val m = r + 48
      b.accept(m, Packet.mrs(8))
      assert(b.decodeOnly(Packet.rd(0, 0)).latency == 9)
      b.violation(m + 8, Packet.rd(0, 2), TMOD, m + 16)
      val r2 = m + 16
      b.accept(r2, Packet.rd(0, 2))
      // CL = 8: r2 + 9 + 8 + 11 = r2 + 28 -> r2 + 32
      b.violation(r2 + 24, Packet.rd(0, 3), TBESL_READ, r2 + 32)
      b.accept(r2 + 32, Packet.rd(0, 3))
    }
  }

  it should "use the same latency for writes (WL = RL)" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 4000)
      val a = b.init(cl = 3)
      b.accept(a, Packet.act(0, 1))
      val w = a + 8
      b.accept(w, Packet.wr(0, 0))
      // CL = 3: w + 4 + 8 + 13 = w + 25 -> w + 32
      b.violation(w + 24, Packet.pre(1), TBESL_WRITE, w + 32)
      b.accept(w + 32, Packet.pre(1))
    }
  }

  it should "enforce tMRD between MRS commands and tMOD before other commands" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.accept(a, Packet.mrs(11))
      b.boundary(a + 4, Packet.mrs(11, nwr = 12), TMRD)
      b.boundary(a + 4 + 12, Packet.act(0, 0), TMOD)
    }
  }

  it should "enforce tWR from the end of write data when it is the binding bound" in {
    // With datasheet values tWR always ends before tBESL(write); a longer tWR
    // shows the bound is still checked.
    test(new RpcTimingChecker(RpcTimingParams.datasheet.copy(tWRPs = 30000))) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.accept(a, Packet.act(1, 1))
      val w = a + 16
      b.accept(w, Packet.wr(1, 0))
      // write data ends at w + 20; tWR = 24 cycles -> w + 44 -> grid w + 48
      b.violation(w + 40, Packet.pre(2), TWR, w + 48)
      b.accept(w + 48, Packet.pre(2))
    }
  }

  it should "refuse reads while Zout is open (section 4 step 4, section 2.13)" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init(zout = 0)
      b.accept(a, Packet.act(0, 0))
      b.violation(a + 16, Packet.rd(0, 0), READ_ZOUT_OPEN, 0)
      b.accept(a + 16, Packet.wr(0, 0))
    }
  }
}
