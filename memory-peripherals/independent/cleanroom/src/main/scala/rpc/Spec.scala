package rpc

/** Numbers taken from the EM6GA16L Rev 1.4 datasheet.
  *
  * Times ending in `Ps` are picoseconds and are converted to device cycles
  * with `ceil(ps / tCK)`. Values ending in `Ck` are already in cycles.
  * docs/TRACEABILITY.md cites the section, table or figure for each field.
  */
case class RpcTimingParams(
    // Table 11-3, Speed-1600 column.
    tRCDPs: Long = 13750,
    tRPPs: Long = 13750,
    tRCPs: Long = 48750,
    tRASPs: Long = 35000,
    tRRDPs: Long = 7500,
    tWRPs: Long = 15000,
    tRESETPs: Long = 5000000,
    tMRDCk: Int = 4,
    tMODCk: Int = 12,
    tMODPs: Long = 15000,
    tPPDIdleCk: Int = 4,
    tPPDActiveCk: Int = 8,
    tBESLReadCk: Int = 9,
    tBESLWriteCk: Int = 11,
    tZQINITPs: Long = 2000000,
    tZQCLPs: Long = 360000,
    tZQCSPs: Long = 90000,
    tZQRESETPs: Long = 50000,
    tREFIFstPs: Long = 100000,
    tREFILpPs: Long = 3200000,
    tRFQSdMaxInREFI: Int = 3,
    tRFQSLPs: Long = 5000,
    tPXCSLPs: Long = 10000,
    tCSLRPs: Long = 2000,
    tckMinPs: Int = 1250,
    // Table 11-3 tCK(avg) rows: CL value -> minimum tCK in ps.
    clMinTckPs: Seq[(Int, Int)] = Seq(3 -> 4000, 8 -> 1667, 10 -> 1500, 11 -> 1250),
    // Sections 2.2 and 3.3: STB is driven low two clocks before the packet.
    stbLeadCk: Int = 2,
    // Table 7-2: RL = AL + CL with AL = 1, WL = RL.
    additiveLatency: Int = 1,
    // Section 2.4: one 32-byte WORD takes 8 bus clocks.
    wordCk: Int = 8,
    // Section 4 step 2: clocks stable for at least 200 us before PU RESET.
    clockStablePs: Long = 200000000L,
    // Table 1-2: RA[0:11].
    rowsPerBank: Int = 4096,
    // Section 5: "under LP RF condition to refresh four full banks will take 64ms".
    lpFourBankPassPs: Long = 64000000000L
) {
  require(lpFourBankPassPs % (4L * tREFILpPs) == 0)

  /** Refresh operations per bank implied by the section 5 64 ms statement. */
  def refreshOpsPerBankFrom64ms: Long = lpFourBankPassPs / (4L * tREFILpPs)

  def clMinTck(cl: Int): Option[Int] = clMinTckPs.collectFirst { case (`cl`, t) => t }
}

object RpcTimingParams {
  val datasheet: RpcTimingParams = RpcTimingParams()
}

/** One row of the tCK(avg) block of Table 11-3. */
case class OperatingPoint(name: String, tckPs: Int, cl: Int, clockMHz: Int, mtps: Int)

object RpcConfig {
  /** Table 11-3 has a single speed column (Speed-1600) with five tCK(avg) rows. */
  val operatingPoints: Seq[OperatingPoint] = Seq(
    OperatingPoint("CL3-250MHz", 4000, 3, 250, 500),
    OperatingPoint("CL8-400MHz", 2500, 8, 400, 800),
    OperatingPoint("CL8-600MHz", 1667, 8, 600, 1200),
    OperatingPoint("CL10-667MHz", 1500, 10, 667, 1333),
    OperatingPoint("CL11-800MHz", 1250, 11, 800, 1600)
  )

  /** MRS CL field encodings, Table 7-2 DB[5:3]. Codes not listed are reserved. */
  val clCodes: Map[Int, Int] = Map(0 -> 8, 1 -> 10, 2 -> 11, 6 -> 3)
  def clCodeFor(cl: Int): Int = clCodes.collectFirst { case (code, `cl`) => code }.getOrElse(
    throw new IllegalArgumentException(s"CL=$cl is not encodable"))

  /** MRS nWR encodings, Table 7-2 DB[8:6]. */
  val nwrCodes: Map[Int, Int] = Map(0 -> 4, 1 -> 6, 2 -> 7, 3 -> 8, 4 -> 10, 5 -> 12, 6 -> 14, 7 -> 16)

  /** Refresh modes: MRS CSRFX (Table 7-2) x REFOP (Table 7-5). */
  case class RefreshMode(name: String, csrfx: Int, refop: Int)
  val refreshModes: Seq[RefreshMode] = Seq(
    RefreshMode("one-shot/FST", 0, 0),
    RefreshMode("one-shot/LP", 0, 1),
    RefreshMode("loop/FST", 1, 0),
    RefreshMode("loop/LP", 1, 1)
  )

  /** refreshSelect values. 0 keeps the unspecified refresh completion visible. */
  val refreshReadings: Seq[(Int, String)] = Seq(
    0 -> "no-collapse",
    1 -> "rows-x-tREFI",
    2 -> "64ms-statement"
  )

  def ceilCycles(ps: Long, tckPs: Int): Long = (ps + tckPs - 1) / tckPs

  def validTck(tckPs: Int, p: RpcTimingParams = RpcTimingParams.datasheet): Boolean =
    tckPs >= p.tckMinPs && tckPs <= 0xffff

  def legalCls(tckPs: Int, p: RpcTimingParams = RpcTimingParams.datasheet): Seq[Int] =
    p.clMinTckPs.filter(_._2 <= tckPs).map(_._1)

  /** Cycle values derived for one clock period; used by docs and tests. */
  case class Derived(tckPs: Int, p: RpcTimingParams) {
    private def c(ps: Long) = ceilCycles(ps, tckPs)
    val tRCD: Long = c(p.tRCDPs)
    val tRP: Long = c(p.tRPPs)
    val tRC: Long = c(p.tRCPs)
    val tRAS: Long = c(p.tRASPs)
    val tRRD: Long = c(p.tRRDPs)
    val tWR: Long = c(p.tWRPs)
    val tRESET: Long = c(p.tRESETPs)
    val tMRD: Long = p.tMRDCk
    val tMOD: Long = math.max(p.tMODCk.toLong, c(p.tMODPs))
    val tZQINIT: Long = c(p.tZQINITPs)
    val tZQCL: Long = c(p.tZQCLPs)
    val tZQCS: Long = c(p.tZQCSPs)
    val tZQRESET: Long = c(p.tZQRESETPs)
    val clockStable: Long = c(p.clockStablePs)

    def rl(cl: Int): Long = p.additiveLatency + cl
    def burstEnd(cmd: Long, cl: Int, words: Int): Long = cmd + rl(cl) + p.wordCk.toLong * words
    def busFreeAfterRead(cmd: Long, cl: Int, words: Int): Long =
      burstEnd(cmd, cl, words) + p.tBESLReadCk + p.stbLeadCk
    def busFreeAfterWrite(cmd: Long, cl: Int, words: Int): Long =
      burstEnd(cmd, cl, words) + p.tBESLWriteCk + p.stbLeadCk

    /** Refresh completion offset (cycles after REF) under reading 1 or 2. */
    def refreshCycles(reading: Int, banks: Int, lp: Boolean, loop: Boolean): Long = {
      val refi = if (lp) p.tREFILpPs else p.tREFIFstPs
      val perBank = reading match {
        case 1 => p.rowsPerBank.toLong
        case 2 => p.refreshOpsPerBankFrom64ms
        case _ => throw new IllegalArgumentException("reading must be 1 or 2")
      }
      val overhead = p.tRFQSdMaxInREFI * refi + p.tRFQSLPs + (if (loop) p.tCSLRPs + p.tPXCSLPs else 0L)
      c(overhead + banks * perBank * refi)
    }
  }

  def derived(tckPs: Int, p: RpcTimingParams = RpcTimingParams.datasheet): Derived = Derived(tckPs, p)
}

/** Decoded command classes reported on `opCode`. */
object Op {
  val NONE = 0
  val MRS = 1
  val ACT = 2
  val RD = 3
  val WR = 4
  val PRE = 5
  val REF = 6
  val PD_ENTRY = 7
  val DPD_ENTRY = 8
  val ZQ = 9
  val RESET = 10
  val UTR = 11
  val UNDEFINED = 15

  val names: Map[Int, String] = Map(
    NONE -> "NONE", MRS -> "MRS", ACT -> "ACT", RD -> "RD", WR -> "WR", PRE -> "PRE",
    REF -> "REF", PD_ENTRY -> "PD_ENTRY", DPD_ENTRY -> "DPD_ENTRY", ZQ -> "ZQ",
    RESET -> "RESET", UTR -> "UTR", UNDEFINED -> "UNDEFINED"
  )
  def name(code: Int): String = names.getOrElse(code, s"OP$code")
}

/** Values of the `kind` output. */
object Kind {
  val NONE = 0
  val ACCEPT = 1
  val VIOLATION = 2
  val INTERPRETATION = 3
}

/** Stable constraint ids reported on `constraintId`. */
object Constraint {
  val NONE = 0
  // Packet encoding and configuration.
  val PKT_UNDEFINED_OPCODE = 1
  val MRS_CL_RESERVED = 2
  val MRS_CL_TCK = 3
  val MRS_RESERVED_BIT = 4
  val REF_REFOP_RESERVED = 5
  val PKT_NO_BANK = 6
  val CFG_TCK_RANGE = 7
  // Power-up and reset sequence.
  val INIT_CLOCK_STABLE = 10
  val INIT_RESET_REQUIRED = 11
  val INIT_TRESET = 12
  val INIT_PREA_REQUIRED = 13
  val INIT_MRS_REQUIRED = 14
  val INIT_ZQINIT_REQUIRED = 15
  // Packet spacing, data bus and busy windows.
  val TPPD_IDLE = 20
  val TPPD_ACTIVE = 21
  val TBESL_READ = 22
  val TBESL_WRITE = 23
  val TMRD = 24
  val TMOD = 25
  val REFRESH_BUSY = 26
  val TZQINIT = 27
  val TZQCL = 28
  val TZQCS = 29
  val TZQRESET = 30
  // Bank state and bank timing.
  val ACT_BANK_ACTIVE = 40
  val TRP = 41
  val TRC = 42
  val TRRD = 43
  val TRCD = 44
  val TRAS = 45
  val TWR = 46
  val RW_BANK_IDLE = 47
  val PRE_BANK_PRECHARGED = 48
  val ZQ_REQUIRES_IDLE = 49
  val UTR_REQUIRES_IDLE = 50
  // Utility-register mode.
  val UTR_MODE_CMD = 60
  // Data path.
  val READ_ZOUT_OPEN = 70
  // Outside the modeled scope.
  val UNMODELED_POWER_DOWN = 80

  val names: Map[Int, String] = Map(
    NONE -> "NONE",
    PKT_UNDEFINED_OPCODE -> "PKT_UNDEFINED_OPCODE",
    MRS_CL_RESERVED -> "MRS_CL_RESERVED",
    MRS_CL_TCK -> "MRS_CL_TCK",
    MRS_RESERVED_BIT -> "MRS_RESERVED_BIT",
    REF_REFOP_RESERVED -> "REF_REFOP_RESERVED",
    PKT_NO_BANK -> "PKT_NO_BANK",
    CFG_TCK_RANGE -> "CFG_TCK_RANGE",
    INIT_CLOCK_STABLE -> "INIT_CLOCK_STABLE",
    INIT_RESET_REQUIRED -> "INIT_RESET_REQUIRED",
    INIT_TRESET -> "INIT_TRESET",
    INIT_PREA_REQUIRED -> "INIT_PREA_REQUIRED",
    INIT_MRS_REQUIRED -> "INIT_MRS_REQUIRED",
    INIT_ZQINIT_REQUIRED -> "INIT_ZQINIT_REQUIRED",
    TPPD_IDLE -> "TPPD_IDLE",
    TPPD_ACTIVE -> "TPPD_ACTIVE",
    TBESL_READ -> "TBESL_READ",
    TBESL_WRITE -> "TBESL_WRITE",
    TMRD -> "TMRD",
    TMOD -> "TMOD",
    REFRESH_BUSY -> "REFRESH_BUSY",
    TZQINIT -> "TZQINIT",
    TZQCL -> "TZQCL",
    TZQCS -> "TZQCS",
    TZQRESET -> "TZQRESET",
    ACT_BANK_ACTIVE -> "ACT_BANK_ACTIVE",
    TRP -> "TRP",
    TRC -> "TRC",
    TRRD -> "TRRD",
    TRCD -> "TRCD",
    TRAS -> "TRAS",
    TWR -> "TWR",
    RW_BANK_IDLE -> "RW_BANK_IDLE",
    PRE_BANK_PRECHARGED -> "PRE_BANK_PRECHARGED",
    ZQ_REQUIRES_IDLE -> "ZQ_REQUIRES_IDLE",
    UTR_REQUIRES_IDLE -> "UTR_REQUIRES_IDLE",
    UTR_MODE_CMD -> "UTR_MODE_CMD",
    READ_ZOUT_OPEN -> "READ_ZOUT_OPEN",
    UNMODELED_POWER_DOWN -> "UNMODELED_POWER_DOWN"
  )
  def name(id: Int): String = names.getOrElse(id, s"C$id")
}
