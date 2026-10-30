package rpc

import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec

import Constraint._

class InitSpec extends AnyFlatSpec with ChiselScalatestTester {
  behavior of "power-up initialization (section 4, Figures 4-1 and 4-2)"

  it should "enforce clock stability, tRESET, tRP, tMOD and tZQINIT at their boundaries (tCK 1250 ps)" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      b.violation(0, Packet.act(0, 0), INIT_RESET_REQUIRED, 0)
      b.boundary(160000, Packet.reset, INIT_CLOCK_STABLE)
      b.violation(160004, Packet.preAll, INIT_TRESET, 164000)
      // A sequence error outranks timing: waiting cannot make this MRS legal.
      b.violation(160004, Packet.mrs(11), INIT_PREA_REQUIRED, 0)
      b.violation(164000, Packet.mrs(11), INIT_PREA_REQUIRED, 0)
      b.violation(164000, Packet.pre(0x3), INIT_PREA_REQUIRED, 0)
      b.accept(164000, Packet.preAll)
      b.violation(164011, Packet.act(0, 0), INIT_MRS_REQUIRED, 0)
      b.boundary(164011, Packet.mrs(11), TRP)
      b.violation(164023, Packet.act(0, 0), INIT_ZQINIT_REQUIRED, 0)
      b.violation(164023, Packet.zq(1), INIT_ZQINIT_REQUIRED, 0)
      b.boundary(164023, Packet.zq(0), TMOD)
      b.boundary(165623, Packet.act(0, 0x10), TZQINIT)
    }
  }

  it should "apply the same sequence at every tCK(avg) row" in {
    for (op <- RpcConfig.operatingPoints) {
      test(new RpcTimingChecker) { dut =>
        val b = new Bench(dut, op.tckPs)
        val d = b.d
        val t0 = d.clockStable
        b.boundary(t0, Packet.reset, INIT_CLOCK_STABLE)
        b.boundary(t0 + d.tRESET, Packet.preAll, INIT_TRESET)
        val tMrs = t0 + d.tRESET + d.tRP
        b.boundary(tMrs, Packet.mrs(op.cl), TRP)
        val tZq = tMrs + d.tMOD
        b.boundary(tZq, Packet.zq(0), TMOD)
        val tAct = tZq + d.tZQINIT
        b.boundary(tAct, Packet.act(1, 7), TZQINIT)
        // In Activate state the next command sits on the 8-cycle grid at or after tRCD.
        val rdAt = tAct + Grid.up8(d.tRCD)
        val early = b.offer(rdAt - 1, Packet.rd(1, 0))
        assert(early.kind == Kind.VIOLATION && early.earliest == rdAt, s"tCK=${op.tckPs}: $early")
        assert(early.cid == (if (rdAt - 1 < tAct + d.tRCD) TRCD else TPPD_ACTIVE))
        b.accept(rdAt, Packet.rd(1, 0))
        assert(b.peek().latency == op.cl + 1)
      }
    }
  }

  it should "reject an MRS whose CL is reserved or too fast for tCK" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      b.accept(160000, Packet.reset)
      b.accept(164000, Packet.preAll)
      b.violation(164011, Packet.mrs(10), MRS_CL_TCK, 0)
      b.violation(164011, Packet.mrs(8), MRS_CL_TCK, 0)
      b.violation(164011, Packet.mrs(3), MRS_CL_TCK, 0)
      b.violation(164011, Packet.mrsRaw(clCode = 3), MRS_CL_RESERVED, 0)
      b.violation(164011, Packet.mrsRaw(clCode = 7), MRS_CL_RESERVED, 0)
      b.violation(164011, Packet.mrsRaw(clCode = 2, fallDb15 = 1), MRS_RESERVED_BIT, 0)
      b.accept(164011, Packet.mrs(11))
    }
  }

  it should "require PRE-all and MRS but not a second ZQINIT after a later reset (Figure 2-3)" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val ready = b.init()
      b.accept(ready, Packet.act(2, 3))
      val r = ready + 8
      b.accept(r, Packet.reset)
      b.boundary(r + 4000, Packet.preAll, INIT_TRESET)
      b.violation(r + 4011, Packet.zq(0), INIT_MRS_REQUIRED, 0)
      b.accept(r + 4011, Packet.mrs(11))
      // Bank 2 was closed by the reset sequence; tMOD applies before any non-MRS command.
      b.violation(r + 4022, Packet.act(2, 3), TMOD, r + 4023)
      b.accept(r + 4023, Packet.act(2, 3))
    }
  }

  it should "reset mode registers to the Table 7-2 defaults" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 2500)
      val ready = b.init(cl = 11)
      b.accept(ready, Packet.reset)
      assert(b.decodeOnly(Packet.rd(0, 0)).latency == 1 + 8) // CL=8 default
    }
  }
}
