package rpc

import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec

class PacketDecodeSpec extends AnyFlatSpec with ChiselScalatestTester {
  "RpcTimingChecker" should "decode every Table 7-1 opcode" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val cases = Seq(
        Packet.mrs(11) -> Op.MRS,
        Packet.act(2, 0xabc) -> Op.ACT,
        Packet.rd(1, 9, 4) -> Op.RD,
        Packet.wr(3, 63, 64) -> Op.WR,
        Packet.pre(0x5) -> Op.PRE,
        Packet.ref(0xf, 1) -> Op.REF,
        Packet.pdEntry -> Op.PD_ENTRY,
        Packet.dpdEntry -> Op.DPD_ENTRY,
        Packet.zq(2) -> Op.ZQ,
        Packet.reset -> Op.RESET,
        Packet.utr(enable = true, 2) -> Op.UTR,
        Packet.join(0x3, 0x0) -> Op.UNDEFINED, // rising DB[2:0] = 011 is unassigned
        Packet.join(0x4, 0x1) -> Op.UNDEFINED, // PRE opcode with falling DB0 = 1
        Packet.join(0x2, 0x3) -> Op.UNDEFINED, // falling DB[2:0] = 011 after rising 010
        Packet.join(0x2, 0x7) -> Op.UNDEFINED
      )
      for ((pkt, op) <- cases) {
        val r = b.decodeOnly(pkt)
        assert(r.op == op, s"${Packet.hex(pkt)} decoded as ${Op.name(r.op)}")
        assert(r.kind == Kind.NONE && !dut.io.accepted.peek().litToBoolean)
      }
    }
  }

  it should "extract bank, row, column and burst length fields" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val a = b.decodeOnly(Packet.act(2, 0xabc))
      assert(a.bank == 2 && a.row == 0xabc)
      val r = b.decodeOnly(Packet.rd(1, 0x2d, 17))
      assert(r.bank == 1 && r.column == 0x2d && r.words == 17)
      val w = b.decodeOnly(Packet.wr(3, 63, 64))
      assert(w.bank == 3 && w.column == 63 && w.words == 64)
      // BC = 0 is a single WORD (Table 7-3)
      assert(b.decodeOnly(Packet.rd(0, 0, 1)).words == 1)
    }
  }

  "Packet" should "place fields at the documented DB positions" in {
    // ACT bank 1 row 0x123: BA0 on rising DB3, RA0..RA11 on falling DB1..DB12
    assert(Packet.act(1, 0x123) == 0x0246000dL)
    // MRS CL=11 nWR=8 Zout=23.7 ohm, ODT open
    assert(Packet.mrs(11) == 0x000002d2L)
    // PRE all banks: BK0..BK3 on rising DB6..DB9
    assert(Packet.preAll == 0x000003c4L)
    // REF bank 0, LP refresh (REFOP0 on falling DB1)
    assert(Packet.ref(1, 1) == 0x00020046L)
    assert(Packet.reset == 0x00010000L)
    assert(Packet.zq(0) == 0x00010001L)
    assert(Packet.pdEntry == 0x00010002L)
    assert(Packet.dpdEntry == 0x00050002L)
  }
}
