package rpc

/** Builds 32-bit parallel request packets (docs/PACKET.md).
  *
  * Bits [15:0] are DB[15:0] on the CLK rising edge and bits [31:16] are
  * DB[15:0] on the following falling edge (Table 7-1). These encoders are
  * stimulus helpers only; the Chisel module does its own decoding.
  */
object Packet {
  private def bit(v: Int, pos: Int): Long = (v.toLong & 1L) << pos
  private def field(v: Int, lo: Int, width: Int): Long = {
    require(v >= 0 && v < (1 << width), s"value $v does not fit $width bits")
    v.toLong << lo
  }
  def join(rise: Long, fall: Long): Long = ((fall & 0xffffL) << 16) | (rise & 0xffffL)

  def mrs(
      cl: Int,
      nwr: Int = 8,
      zout: Int = 1,
      odt: Int = 0,
      stbOdt: Int = 0,
      csrfx: Int = 0,
      odtPd: Int = 0
  ): Long = mrsRaw(RpcConfig.clCodeFor(cl), nwrCode(nwr), zout, odt, stbOdt, csrfx, odtPd)

  def mrsRaw(
      clCode: Int,
      nwrCode: Int = 3,
      zout: Int = 1,
      odt: Int = 0,
      stbOdt: Int = 0,
      csrfx: Int = 0,
      odtPd: Int = 0,
      fallDb15: Int = 0
  ): Long = {
    val rise = field(odt, 13, 3) | field(zout, 9, 4) | field(nwrCode, 6, 3) | field(clCode, 3, 3) | 0x2L
    val fall = bit(fallDb15, 15) | bit(odtPd, 14) | bit(csrfx, 13) | bit(stbOdt, 12)
    join(rise, fall)
  }

  def nwrCode(nwr: Int): Int = RpcConfig.nwrCodes.collectFirst { case (code, `nwr`) => code }.getOrElse(
    throw new IllegalArgumentException(s"nWR=$nwr is not encodable"))

  def act(bank: Int, row: Int): Long =
    join(field(bank, 3, 2) | 0x5L, field(row, 1, 12))

  /** Column is the WORD address CA[9:4]; words is 1..64 (BC = words - 1). */
  def rd(bank: Int, column: Int, words: Int = 1): Long = columnCmd(bank, column, words, 0)
  def wr(bank: Int, column: Int, words: Int = 1): Long = columnCmd(bank, column, words, 1)

  private def columnCmd(bank: Int, col: Int, words: Int, op: Int): Long = {
    require(words >= 1 && words <= 64)
    require(col >= 0 && col < 64)
    val ca4to6 = col & 0x7
    val ca7to9 = (col >> 3) & 0x7
    val rise = field(ca4to6, 13, 3) | field(words - 1, 5, 6) | field(bank, 3, 2) | op.toLong
    join(rise, field(ca7to9, 13, 3))
  }

  /** mask bit i selects bank i (BK0..BK3 on DB6..DB9). */
  def pre(mask: Int): Long = join(field(mask, 6, 4) | 0x4L, 0)
  def preAll: Long = pre(0xf)

  /** refop: 0 = FST (tREFI 100 ns), 1 = LP (tREFI 3.2 us); 2 and 3 are reserved. */
  def ref(mask: Int, refop: Int = 0): Long = join(field(mask, 6, 4) | 0x6L, field(refop, 1, 2))

  /** zqop: 0 = ZQINIT, 1 = ZQCL, 2 = ZQCS, 3 = ZQRESET (Table 7-4). */
  def zq(zqop: Int): Long = join(field(zqop, 14, 2) | 0x1L, 0x1L)

  def reset: Long = join(0x0L, 0x1L)

  def utr(enable: Boolean, utrOp: Int = 0): Long =
    join(field(utrOp, 4, 2) | bit(if (enable) 1 else 0, 3) | 0x7L, 0)

  def pdEntry: Long = join(0x2L, 0x1L)
  def dpdEntry: Long = join(0x2L, 0x5L)

  def hex(packet: Long): String = f"$packet%08x"
}
