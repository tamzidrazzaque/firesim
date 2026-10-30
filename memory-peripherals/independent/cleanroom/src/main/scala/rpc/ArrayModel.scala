package rpc

import scala.collection.mutable

/** Sparse byte array for one device, addressed by (bank, row, WORD column).
  *
  * The caller applies a command here only after RpcTimingChecker accepted it,
  * using the bank/row/column/words fields peeked from the module. A WORD is
  * 32 bytes (section 2.4); bursts wrap inside the 64-WORD page (sections 2.5,
  * 2.6, 3.1). Bytes never written read as zero; the datasheet does not
  * define power-up contents.
  */
class ArrayModel {
  val wordBytes = 32
  val wordsPerPage = 64
  private val words = mutable.Map[(Int, Int, Int), Array[Byte]]()

  private def word(bank: Int, row: Int, col: Int): Array[Byte] =
    words.getOrElseUpdate((bank, row, col % wordsPerPage), new Array[Byte](wordBytes))

  /** Byte write mask semantics of sections 2.6/2.7 and Table 2-2: a set bit
    * masks (does not write) that byte. `firstMask` applies only to the first
    * WORD and `lastMask` only to the last WORD; a one-WORD burst gets both.
    */
  def write(bank: Int, row: Int, col: Int, data: Seq[Array[Byte]], firstMask: Long, lastMask: Long): Unit = {
    require(data.nonEmpty && data.size <= wordsPerPage)
    data.zipWithIndex.foreach { case (bytes, n) =>
      require(bytes.length == wordBytes)
      val mask = (if (n == 0) firstMask else 0L) | (if (n == data.size - 1) lastMask else 0L)
      val target = word(bank, row, col + n)
      for (b <- 0 until wordBytes if ((mask >> b) & 1L) == 0L) target(b) = bytes(b)
    }
  }

  def read(bank: Int, row: Int, col: Int, count: Int): Seq[Array[Byte]] =
    (0 until count).map(n => word(bank, row, col + n).clone())
}
