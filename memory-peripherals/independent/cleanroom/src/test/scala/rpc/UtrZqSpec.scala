package rpc

import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec

import Constraint._

class UtrZqSpec extends AnyFlatSpec with ChiselScalatestTester {
  behavior of "utility register mode (section 2.14, Table 7-6)"

  it should "allow only RD, UTR and RESET while UTR mode is on" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.accept(a, Packet.utr(enable = true, 1))
      // UTR changes the mode register state: tMOD before the first RD.
      b.boundary(a + 12, Packet.rd(0, 0), TMOD)
      val r = a + 12
      // Device stays Idle: bus free at r + 12 + 8 + 9 + 2 = r + 31, no 8-cycle grid.
      b.boundary(r + 31, Packet.rd(3, 0, words = 2), TBESL_READ)
      val r2 = r + 31
      b.violation(r2 + 20, Packet.act(0, 0), UTR_MODE_CMD, 0)
      b.violation(r2 + 20, Packet.wr(0, 0), UTR_MODE_CMD, 0)
      b.violation(r2 + 20, Packet.mrs(11), UTR_MODE_CMD, 0)
      b.violation(r2 + 20, Packet.zq(2), UTR_MODE_CMD, 0)
      // r2 + 12 + 16 + 11 = r2 + 39
      b.boundary(r2 + 39, Packet.utr(enable = false), TBESL_READ)
      val u = r2 + 39
      b.boundary(u + 12, Packet.act(0, 0), TMOD)
    }
  }

  it should "require all banks idle before entering UTR mode" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.accept(a, Packet.act(2, 0))
      b.violation(a + 40, Packet.utr(enable = true), UTR_REQUIRES_IDLE, 0)
      b.accept(a + 40, Packet.pre(4))
      b.boundary(a + 51, Packet.utr(enable = true), TRP)
    }
  }

  behavior of "ZQ calibration (Tables 7-4 and 11-3)"

  it should "hold the device for tZQCS, tZQCL and tZQRESET" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.accept(a, Packet.zq(2))
      b.boundary(a + 72, Packet.act(0, 0), TZQCS)
      val act = a + 72
      b.violation(act + 32, Packet.zq(1), ZQ_REQUIRES_IDLE, 0)
      b.accept(act + 32, Packet.pre(1))
      val p = act + 32
      b.boundary(p + 11, Packet.zq(1), TRP)
      val zcl = p + 11
      b.boundary(zcl + 288, Packet.zq(3), TZQCL)
      val zr = zcl + 288
      b.boundary(zr + 40, Packet.act(0, 0), TZQRESET)
    }
  }

  it should "scale ZQ times with tCK (tCK 4000 ps: tZQCS = 23)" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 4000)
      val a = b.init(cl = 3)
      b.accept(a, Packet.zq(2))
      b.boundary(a + 23, Packet.zq(3), TZQCS)
      b.boundary(a + 23 + 13, Packet.act(0, 0), TZQRESET)
    }
  }

  behavior of "commands outside the modeled scope"

  it should "report power-down entries as INTERPRETATION without changing state" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.interpretation(a, Packet.pdEntry, UNMODELED_POWER_DOWN, 0)
      b.interpretation(a, Packet.dpdEntry, UNMODELED_POWER_DOWN, 0)
      // the device is still Idle and the tPPD reference has not moved
      b.accept(a, Packet.act(0, 0))
      // an early power-down entry is still a timing violation
      b.violation(a + 3, Packet.pdEntry, TPPD_ACTIVE, a + 8)
    }
  }

  it should "reject undefined opcodes at any time" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      b.violation(0, Packet.join(0x3, 0), PKT_UNDEFINED_OPCODE, 0)
      val a = b.init()
      b.violation(a, Packet.join(0x2, 0x7), PKT_UNDEFINED_OPCODE, 0)
      b.accept(a, Packet.act(0, 0))
    }
  }

  it should "reject a clock period below tCK(avg) min" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1249)
      b.violation(200000, Packet.reset, CFG_TCK_RANGE, 0)
    }
  }

  it should "report the idle tPPD when two packets are closer than 4 cycles" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.accept(a, Packet.mrs(11))
      // tMOD does not apply to RESET, so only tPPD(idle) separates the packets.
      b.boundary(a + 4, Packet.reset, TPPD_IDLE)
    }
  }
}
