package rpc

import chisel3.{assert => _, _}
import chiseltest._
import org.scalatest.Assertions._

/** One peeked result from RpcTimingChecker. */
case class Res(
    kind: Int,
    cid: Int,
    earliest: BigInt,
    op: Int,
    e1: BigInt,
    e2: BigInt,
    bank: Int,
    row: Int,
    column: Int,
    words: Int,
    latency: Int
) {
  def accepted: Boolean = kind == Kind.ACCEPT
  override def toString: String = {
    val k = kind match {
      case Kind.ACCEPT => "ACCEPT"
      case Kind.VIOLATION => "VIOLATION"
      case Kind.INTERPRETATION => "INTERPRETATION"
      case _ => "NONE"
    }
    s"$k ${Constraint.name(cid)} earliest=$earliest op=${Op.name(op)} rs1=$e1 rs2=$e2"
  }
}

/** Drives the checker one command per clock and checks peeked outputs. */
class Bench(val dut: RpcTimingChecker, val tck: Int, refreshSelect: Int = 1) {
  val d: RpcConfig.Derived = RpcConfig.derived(tck)
  dut.io.tckPs.poke(tck.U)
  dut.io.refreshSelect.poke(refreshSelect.U)
  dut.io.valid.poke(false.B)

  def peek(): Res = Res(
    dut.io.kind.peek().litValue.toInt,
    dut.io.constraintId.peek().litValue.toInt,
    dut.io.earliest.peek().litValue,
    dut.io.opCode.peek().litValue.toInt,
    dut.io.earliestRs1.peek().litValue,
    dut.io.earliestRs2.peek().litValue,
    dut.io.bank.peek().litValue.toInt,
    dut.io.row.peek().litValue.toInt,
    dut.io.column.peek().litValue.toInt,
    dut.io.words.peek().litValue.toInt,
    dut.io.latency.peek().litValue.toInt
  )

  def offer(cycle: Long, packet: Long): Res = {
    dut.io.valid.poke(true.B)
    dut.io.cycle.poke(BigInt(cycle).U(64.W))
    dut.io.packet.poke(packet.U(32.W))
    val r = peek()
    if (r.accepted) assert(dut.io.accepted.peek().litToBoolean) else assert(!dut.io.accepted.peek().litToBoolean)
    dut.clock.step()
    dut.io.valid.poke(false.B)
    r
  }

  def decodeOnly(packet: Long): Res = {
    dut.io.valid.poke(false.B)
    dut.io.packet.poke(packet.U(32.W))
    peek()
  }

  def accept(cycle: Long, packet: Long): Res = {
    val r = offer(cycle, packet)
    assert(r.accepted, s"expected ACCEPT at $cycle for ${Packet.hex(packet)}, got $r")
    r
  }

  /** earliest = 0 means "no wait makes it legal". */
  def violation(cycle: Long, packet: Long, cid: Int, earliest: Long): Res = {
    val r = offer(cycle, packet)
    assert(
      r.kind == Kind.VIOLATION && r.cid == cid && r.earliest == earliest,
      s"expected VIOLATION ${Constraint.name(cid)} earliest=$earliest at $cycle, got $r"
    )
    r
  }

  def interpretation(cycle: Long, packet: Long, cid: Int, earliest: Long): Res = {
    val r = offer(cycle, packet)
    assert(
      r.kind == Kind.INTERPRETATION && r.cid == cid && r.earliest == earliest,
      s"expected INTERPRETATION ${Constraint.name(cid)} earliest=$earliest at $cycle, got $r"
    )
    r
  }

  /** Boundary check: illegal one cycle early (reporting `cid` and the
    * boundary as earliest), then legal at the boundary.
    */
  def boundary(at: Long, packet: Long, cid: Int): Res = {
    violation(at - 1, packet, cid, at)
    accept(at, packet)
  }

  def defaultCl: Int =
    RpcConfig.operatingPoints.find(_.tckPs == tck).map(_.cl).getOrElse(RpcConfig.legalCls(tck).max)

  /** Section 4 power-up sequence; returns the first cycle a normal command may use. */
  def init(cl: Int = defaultCl, csrfx: Int = 0, zout: Int = 1): Long = {
    val t0 = d.clockStable
    accept(t0, Packet.reset)
    val tPrea = t0 + d.tRESET
    accept(tPrea, Packet.preAll)
    val tMrs = tPrea + d.tRP
    accept(tMrs, Packet.mrs(cl, csrfx = csrfx, zout = zout))
    val tZq = tMrs + d.tMOD
    accept(tZq, Packet.zq(0))
    tZq + d.tZQINIT
  }
}

object Grid {
  def up8(x: Long): Long = (x + 7) / 8 * 8
}
