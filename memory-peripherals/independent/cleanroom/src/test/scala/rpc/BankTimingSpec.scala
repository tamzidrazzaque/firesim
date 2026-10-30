package rpc

import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec

import Constraint._

class BankTimingSpec extends AnyFlatSpec with ChiselScalatestTester {
  behavior of "bank timing and 8-cycle clocking (Table 11-3, sections 2.8, 2.9, 2.15)"

  it should "hold RD until tRCD rounded up to the 8-cycle grid (tCK 1250 ps: tRCD = 11)" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.accept(a, Packet.act(0, 0x40))
      b.violation(a + 8, Packet.rd(0, 0), TRCD, a + 16)
      b.violation(a + 10, Packet.rd(0, 0), TRCD, a + 16)
      b.violation(a + 11, Packet.rd(0, 0), TPPD_ACTIVE, a + 16)
      b.boundary(a + 16, Packet.rd(0, 0), TPPD_ACTIVE)
    }
  }

  it should "let tRCD scale with tCK (tCK 4000 ps: tRCD = 4, grid = 8)" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 4000)
      val a = b.init(cl = 3)
      b.accept(a, Packet.act(1, 1))
      b.violation(a + 3, Packet.rd(1, 0), TRCD, a + 8)
      b.boundary(a + 8, Packet.rd(1, 0), TPPD_ACTIVE)
    }
  }

  it should "report the next grid slot for an off-grid command in Activate state" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.accept(a, Packet.act(0, 0))
      b.violation(a + 17, Packet.rd(0, 0), TPPD_ACTIVE, a + 24)
      b.accept(a + 24, Packet.rd(0, 0))
    }
  }

  it should "enforce tRRD between ACTs of different banks" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.accept(a, Packet.act(0, 0))
      b.violation(a + 5, Packet.act(1, 0), TRRD, a + 8)
      b.violation(a + 7, Packet.act(1, 0), TPPD_ACTIVE, a + 8)
      b.accept(a + 8, Packet.act(1, 0))
    }
  }

  it should "enforce tRAS before PRE and tRP before re-activating" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.accept(a, Packet.act(0, 5))
      b.violation(a + 24, Packet.pre(1), TRAS, a + 32)
      b.violation(a + 31, Packet.pre(1), TPPD_ACTIVE, a + 32)
      b.accept(a + 32, Packet.pre(1))
      val p = a + 32
      // All banks closed: Idle is entered when the precharge completes (tRP = 11).
      b.boundary(p + 11, Packet.act(0, 6), TRP)
    }
  }

  it should "keep 8-cycle clocking until the last precharge completes (section 2.9)" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.accept(a, Packet.act(0, 5))
      val p = a + 32
      b.accept(p, Packet.pre(1))
      // Bank 1 needs no tRP, but tRP of bank 0 has not elapsed: still Activate state.
      b.violation(p + 4, Packet.act(1, 0), TPPD_ACTIVE, p + 8)
      b.accept(p + 8, Packet.act(1, 0))
    }
  }

  it should "use the 4-cycle idle tPPD once the device is Idle" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.accept(a, Packet.act(0, 5))
      val p = a + 32
      b.accept(p, Packet.pre(1))
      // p + 13 is off the 8-cycle grid but the device is Idle from p + 11.
      b.accept(p + 13, Packet.act(1, 0))
    }
  }

  it should "enforce tRC from ACT to REF" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.accept(a, Packet.act(3, 5))
      b.violation(a + 32, Packet.ref(0x8), TRC, a + 40)
      b.violation(a + 39, Packet.ref(0x8), TPPD_ACTIVE, a + 40)
      b.accept(a + 40, Packet.ref(0x8))
    }
  }

  behavior of "bank state (Tables 8-3 and 8-4)"

  it should "reject commands that waiting cannot make legal" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.violation(a, Packet.rd(0, 0), RW_BANK_IDLE, 0)
      b.violation(a, Packet.wr(0, 0), RW_BANK_IDLE, 0)
      b.violation(a, Packet.pre(1), PRE_BANK_PRECHARGED, 0)
      b.accept(a, Packet.act(0, 1))
      b.violation(a + 40, Packet.act(0, 2), ACT_BANK_ACTIVE, 0)
      // PRE to an already precharged bank is illegal (note 11), also inside a multi-bank PRE.
      b.violation(a + 40, Packet.preAll, PRE_BANK_PRECHARGED, 0)
      b.violation(a + 40, Packet.pre(0), PKT_NO_BANK, 0)
      b.accept(a + 40, Packet.pre(1))
      b.violation(a + 80, Packet.pre(1), PRE_BANK_PRECHARGED, 0)
    }
  }

  it should "not update bank state for an early command" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.accept(a, Packet.act(0, 1))
      // Early ACT of bank 1 is reported and does not open bank 1 ...
      b.violation(a + 4, Packet.act(1, 1), TRRD, a + 8)
      b.violation(a + 16, Packet.rd(1, 0), RW_BANK_IDLE, 0)
      // ... and does not move the tPPD reference: a + 8 is still a legal slot.
      b.accept(a + 8, Packet.act(1, 1))
      // Early PRE of bank 0 is reported and bank 0 stays open.
      b.violation(a + 16, Packet.pre(1), TRAS, a + 32)
      b.accept(a + 24, Packet.rd(0, 0))
    }
  }

  it should "leave every bank precharged after REF" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.init()
      b.accept(a, Packet.act(0, 1))
      b.accept(a + 40, Packet.ref(0x2))
      b.violation(a + 48, Packet.pre(1), PRE_BANK_PRECHARGED, 0)
      b.violation(a + 48, Packet.rd(0, 0), RW_BANK_IDLE, 0)
    }
  }
}
