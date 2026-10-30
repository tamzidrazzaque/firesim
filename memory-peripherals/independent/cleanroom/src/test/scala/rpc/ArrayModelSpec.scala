package rpc

import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec

class ArrayModelSpec extends AnyFlatSpec with ChiselScalatestTester {
  private def pattern(seed: Int, n: Int): Seq[Array[Byte]] =
    (0 until n).map(w => Array.tabulate[Byte](32)(i => (seed * 31 + w * 7 + i).toByte))

  "ArrayModel" should "apply write masks to the first and last WORD only" in {
    val m = new ArrayModel
    val data = pattern(1, 3)
    m.write(0, 1, 62, data, firstMask = 0x1L, lastMask = 0x80000000L)
    val back = m.read(0, 1, 62, 3)
    assert(back(0)(0) == 0 && back(0).drop(1).sameElements(data(0).drop(1)))
    assert(back(1).sameElements(data(1)))
    assert(back(2)(31) == 0 && back(2).take(31).sameElements(data(2).take(31)))
    // column 62 + 2 wraps to column 0 of the same page
    assert(m.read(0, 1, 0, 1).head.sameElements(back(2)))
  }

  it should "OR both masks for a single-WORD burst" in {
    val m = new ArrayModel
    m.write(1, 0, 0, pattern(2, 1), firstMask = 0x1L, lastMask = 0x2L)
    val w = m.read(1, 0, 0, 1).head
    assert(w(0) == 0 && w(1) == 0 && w(2) == pattern(2, 1).head(2))
  }

  "RpcTimingChecker with ArrayModel" should "change array contents only for accepted commands" in {
    test(new RpcTimingChecker) { dut =>
      val b = new Bench(dut, 1250)
      val m = new ArrayModel
      def drive(cycle: Long, pkt: Long, data: Seq[Array[Byte]] = Nil): Res = {
        val r = b.offer(cycle, pkt)
        if (r.accepted && r.op == Op.WR) m.write(r.bank, r.row, r.column, data.take(r.words), 0L, 0L)
        r
      }
      val a = b.init()
      assert(drive(a, Packet.act(2, 0x155)).accepted)
      // early write: reported, array untouched
      val early = drive(a + 8, Packet.wr(2, 10, 2), pattern(9, 2))
      assert(early.kind == Kind.VIOLATION && early.cid == Constraint.TRCD)
      assert(m.read(2, 0x155, 10, 2).forall(_.forall(_ == 0)))
      val w = drive(a + 16, Packet.wr(2, 10, 2), pattern(3, 2))
      assert(w.accepted && w.row == 0x155 && w.words == 2)
      // write data ends at a + 44, tBESL(write) + STB lead -> a + 57 -> grid a + 64
      val rd = b.offer(a + 64, Packet.rd(2, 10, 2))
      assert(rd.accepted && rd.row == 0x155)
      val got = m.read(rd.bank, rd.row, rd.column, rd.words)
      assert(got.zip(pattern(3, 2)).forall { case (x, y) => x.sameElements(y) })
    }
  }
}
