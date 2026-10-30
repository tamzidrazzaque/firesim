package rpc

import chisel3._
import chisel3.util._

class RpcTimingCheckerIO extends Bundle {
  val valid = Input(Bool())
  val cycle = Input(UInt(64.W))
  val packet = Input(UInt(32.W))
  val tckPs = Input(UInt(16.W))
  val refreshSelect = Input(UInt(2.W))

  val accepted = Output(Bool())
  val kind = Output(UInt(2.W))
  val constraintId = Output(UInt(8.W))
  val earliest = Output(UInt(64.W))
  val opCode = Output(UInt(4.W))

  // Earliest legal cycle under refreshSelect readings 1 and 2 (0 for a
  // state violation). They differ only while a refresh is outstanding.
  val earliestRs1 = Output(UInt(64.W))
  val earliestRs2 = Output(UInt(64.W))
  // Decoded address fields; `row` is the open row of `bank` for RD/WR.
  val bank = Output(UInt(2.W))
  val row = Output(UInt(12.W))
  val column = Output(UInt(6.W))
  val words = Output(UInt(7.W))
  // RL = WL = AL + CL from the current mode register, counted from the
  // packet's rising clock edge to the first data (or WL-2 mask) beat.
  val latency = Output(UInt(5.W))
}

/** Timing and bank-state checker for one EM6GA16L in parallel-packet mode.
  *
  * Outputs are combinational in the offered command. State is committed on
  * the next clock edge only when the command is accepted, or when it is an
  * INTERPRETATION whose sole open question is refresh completion (the
  * command is then applied as if refresh had finished by the offered cycle).
  */
class RpcTimingChecker(val p: RpcTimingParams = RpcTimingParams.datasheet) extends Module {
  val io = IO(new RpcTimingCheckerIO)

  private val W = 64
  require(isPow2(p.tPPDActiveCk))
  require(isPow2(p.wordCk))
  require(p.refreshOpsPerBankFrom64ms >= p.rowsPerBank)

  private val now = io.cycle
  private val tck = Mux(io.tckPs === 0.U, 1.U(16.W), io.tckPs)
  private def cyc(ps: UInt): UInt = (ps +& (tck - 1.U)) / tck
  private def cycPs(ps: Long): UInt = cyc(ps.U)
  private def maxU(a: UInt, b: UInt): UInt = Mux(a > b, a, b)
  private def minU(a: UInt, b: UInt): UInt = Mux(a < b, a, b)

  // ---------------------------------------------------------------- decode
  // Table 7-1: opcode is DB[2:0] on the rising edge plus DB[0] (and for
  // PD/DPD DB[2:1]) on the falling edge.
  private val rise = io.packet(15, 0)
  private val fall = io.packet(31, 16)
  private val op = WireDefault(Op.UNDEFINED.U(4.W))
  private val f0 = fall(0)
  private val f21 = fall(2, 1)
  switch(rise(2, 0)) {
    is(0.U) { op := Mux(f0, Op.RESET.U, Op.RD.U) }
    is(1.U) { op := Mux(f0, Op.ZQ.U, Op.WR.U) }
    is(2.U) {
      op := Mux(!f0, Op.MRS.U, Mux(f21 === 0.U, Op.PD_ENTRY.U, Mux(f21 === 2.U, Op.DPD_ENTRY.U, Op.UNDEFINED.U)))
    }
    is(4.U) { op := Mux(f0, Op.UNDEFINED.U, Op.PRE.U) }
    is(5.U) { op := Mux(f0, Op.UNDEFINED.U, Op.ACT.U) }
    is(6.U) { op := Mux(f0, Op.UNDEFINED.U, Op.REF.U) }
    is(7.U) { op := Mux(f0, Op.UNDEFINED.U, Op.UTR.U) }
  }
  private def isOp(o: Int): Bool = op === o.U
  private val isMrs = isOp(Op.MRS)
  private val isAct = isOp(Op.ACT)
  private val isRd = isOp(Op.RD)
  private val isWr = isOp(Op.WR)
  private val isPre = isOp(Op.PRE)
  private val isRef = isOp(Op.REF)
  private val isZq = isOp(Op.ZQ)
  private val isReset = isOp(Op.RESET)
  private val isUtr = isOp(Op.UTR)
  private val isPd = isOp(Op.PD_ENTRY) || isOp(Op.DPD_ENTRY)
  private val isUndef = isOp(Op.UNDEFINED)

  private val ba = rise(4, 3)
  private val actRow = fall(12, 1)
  private val col = Cat(fall(15, 13), rise(15, 13)) // CA9..CA4
  private val words = rise(10, 5) +& 1.U // Table 7-3: BC + 1 WORDs
  private val bankMask = rise(9, 6) // bit i = BKi
  private val refop = fall(2, 1) // {REFOP1, REFOP0}
  private val zqop = rise(15, 14) // {ZQCOP1, ZQCOP0}
  private val utrEn = rise(3)
  private val utrOp = rise(5, 4)
  private val mOdt = rise(15, 13)
  private val mZout = rise(12, 9)
  private val mNwr = rise(8, 6)
  private val mCl = rise(5, 3)
  private val mFixed = fall(15)
  private val mOdtPd = fall(14)
  private val mCsrfx = fall(13)
  private val mStbOdt = fall(12)

  private def clValue(code: UInt): UInt = {
    val v = WireDefault(0.U(5.W))
    for ((c, cl) <- RpcConfig.clCodes) when(code === c.U) { v := cl.U }
    v
  }
  private def clReserved(code: UInt): Bool = !RpcConfig.clCodes.keys.map(c => code === c.U).reduce(_ || _)
  private def clMinTck(code: UInt): UInt = {
    val v = WireDefault(0xffff.U(16.W))
    for ((c, cl) <- RpcConfig.clCodes; t <- p.clMinTck(cl)) when(code === c.U) { v := t.U }
    v
  }

  // ----------------------------------------------------------------- state
  private def vec4[T <: Data](init: T): Vec[T] = RegInit(VecInit(Seq.fill(4)(init)))

  private val everReset = RegInit(false.B)
  private val resetAt = RegInit(0.U(W.W))
  private val needPrea = RegInit(false.B)
  private val needMrs = RegInit(false.B)
  private val needZqInit = RegInit(true.B)

  private val havePrev = RegInit(false.B)
  private val prevAt = RegInit(0.U(W.W))

  private val bankOpen = vec4(false.B)
  private val bankKnown = vec4(false.B)
  private val openRow = vec4(0.U(12.W))
  private val actValid = vec4(false.B)
  private val actAt = vec4(0.U(W.W))
  private val preValid = vec4(false.B)
  private val preAt = vec4(0.U(W.W))
  private val wrValid = vec4(false.B)
  private val wrEndAt = vec4(0.U(W.W))
  private val actAnyValid = RegInit(false.B)
  private val actAnyAt = RegInit(0.U(W.W))

  private val burstValid = RegInit(false.B)
  private val burstWrite = RegInit(false.B)
  private val burstEnd = RegInit(0.U(W.W))

  private val modeValid = RegInit(false.B)
  private val modeWasMrs = RegInit(false.B)
  private val modeAt = RegInit(0.U(W.W))

  // Mode register with the Table 7-2 defaults.
  private val mrCl = RegInit(0.U(3.W))
  private val mrNwr = RegInit(3.U(3.W))
  private val mrZout = RegInit(0.U(4.W))
  private val mrOdt = RegInit(0.U(3.W))
  private val mrStbOdt = RegInit(false.B)
  private val mrCsrfx = RegInit(false.B)
  private val mrOdtPd = RegInit(false.B)

  private val utrMode = RegInit(false.B)
  private val utrOpR = RegInit(0.U(2.W))

  private val zqValid = RegInit(false.B)
  private val zqAt = RegInit(0.U(W.W))
  private val zqOpR = RegInit(0.U(2.W))

  private val refPending = RegInit(false.B)
  private val refAt = RegInit(0.U(W.W))
  private val refBanks = RegInit(0.U(3.W))
  private val refLp = RegInit(false.B)
  private val refLoop = RegInit(false.B)

  // --------------------------------------------------------- cycle values
  private val cRCD = cycPs(p.tRCDPs)
  private val cRP = cycPs(p.tRPPs)
  private val cRC = cycPs(p.tRCPs)
  private val cRAS = cycPs(p.tRASPs)
  private val cRRD = cycPs(p.tRRDPs)
  private val cWR = cycPs(p.tWRPs)
  private val cRESET = cycPs(p.tRESETPs)
  private val cMOD = maxU(p.tMODCk.U, cycPs(p.tMODPs))
  private val cClockStable = cycPs(p.clockStablePs)
  private val zqCycles =
    VecInit(Seq(cycPs(p.tZQINITPs), cycPs(p.tZQCLPs), cycPs(p.tZQCSPs), cycPs(p.tZQRESETPs)))(zqOpR)
  private val zqIds = VecInit(
    Seq(Constraint.TZQINIT, Constraint.TZQCL, Constraint.TZQCS, Constraint.TZQRESET).map(_.U(8.W))
  )(zqOpR)

  // Section 5 / Table 11-3: REF -> BUSY within tRFQSd (max 3 tREFI), one pass
  // over the selected banks, DQS low for tRFQSL; loop mode adds the CS# exit
  // pulse (tCSLR) and tPXCSL. Only the pass length differs between readings.
  private val refiPs = Mux(refLp, p.tREFILpPs.U, p.tREFIFstPs.U)
  private val refOverheadPs =
    refiPs * p.tRFQSdMaxInREFI.U +& p.tRFQSLPs.U +& Mux(refLoop, (p.tCSLRPs + p.tPXCSLPs).U, 0.U)
  private def refDone(perBank: Long): UInt = refAt + cyc(refOverheadPs +& refBanks * perBank.U * refiPs)
  private val refDone1 = refDone(p.rowsPerBank.toLong)
  private val refDone2 = refDone(p.refreshOpsPerBankFrom64ms)

  // ---------------------------------------------------------- lower bounds
  private class Bounds {
    var at: UInt = 0.U(W.W)
    var id: UInt = Constraint.NONE.U(8.W)
    def add(cond: Bool, bound: UInt, cid: UInt): Unit = {
      val take = cond && bound > at
      at = Mux(take, bound, at)
      id = Mux(take, cid, id)
    }
    def add(cond: Bool, bound: UInt, cid: Int): Unit = add(cond, bound, cid.U(8.W))
  }

  private val base = new Bounds
  base.add(!everReset && isReset, cClockStable, Constraint.INIT_CLOCK_STABLE)
  base.add(everReset, resetAt + cRESET, Constraint.INIT_TRESET)
  base.add(burstValid && !burstWrite, burstEnd + (p.tBESLReadCk + p.stbLeadCk).U, Constraint.TBESL_READ)
  base.add(burstValid && burstWrite, burstEnd + (p.tBESLWriteCk + p.stbLeadCk).U, Constraint.TBESL_WRITE)
  base.add(zqValid, zqAt + zqCycles, zqIds)
  base.add(modeValid && isMrs && modeWasMrs, modeAt + p.tMRDCk.U, Constraint.TMRD)
  base.add(modeValid && !isReset && !(isMrs && modeWasMrs), modeAt + cMOD, Constraint.TMOD)
  private val columnAccess = (isRd && !utrMode) || isWr
  for (i <- 0 until 4) {
    val sel = ba === i.U
    base.add(isAct && sel && preValid(i), preAt(i) + cRP, Constraint.TRP)
    base.add(isAct && sel && actValid(i), actAt(i) + cRC, Constraint.TRC)
    base.add(columnAccess && sel && actValid(i), actAt(i) + cRCD, Constraint.TRCD)
    base.add(isPre && bankMask(i) && actValid(i), actAt(i) + cRAS, Constraint.TRAS)
    base.add(isPre && bankMask(i) && wrValid(i), wrEndAt(i) + cWR, Constraint.TWR)
    base.add(isRef && actValid(i), actAt(i) + cRC, Constraint.TRC)
    base.add((isMrs || isZq || isUtr) && preValid(i), preAt(i) + cRP, Constraint.TRP)
  }
  base.add(isAct && actAnyValid, actAnyAt + cRRD, Constraint.TRRD)

  private def withRefresh(done: UInt): (UInt, UInt) = {
    val take = refPending && done > base.at
    (Mux(take, done, base.at), Mux(take, Constraint.REFRESH_BUSY.U(8.W), base.id))
  }
  private val (bound1, id1) = withRefresh(refDone1)
  private val (bound2, id2) = withRefresh(refDone2)

  // ------------------------------------------- tPPD and 8-cycle clocking
  // Sections 2.8/2.9, Table 11-3 tPPD: while any bank is open or a
  // precharge has not completed (tRP) the gap from the previous parallel
  // command must be a multiple of 8 tCK; in Idle it must be >= 4 tCK.
  private val anyOpen = bankOpen.asUInt.orR
  private val idleAt = (0 until 4).map(i => Mux(preValid(i), preAt(i) + cRP, 0.U(W.W))).reduce(maxU)
  private val activeAtNow = anyOpen || now < idleAt
  private val gridShift = log2Ceil(p.tPPDActiveCk)

  private def earliestFrom(bound: UInt): UInt = {
    val lower = maxU(bound, now)
    val g0 = maxU(lower, prevAt + p.tPPDActiveCk.U)
    val slot = prevAt + ((((g0 - prevAt) + (p.tPPDActiveCk - 1).U) >> gridShift) << gridShift)
    val idleSlot = maxU(maxU(lower, prevAt + p.tPPDIdleCk.U), idleAt)
    Mux(havePrev, Mux(anyOpen, slot, minU(slot, idleSlot)), lower)
  }
  private def failId(bound: UInt, id: UInt): UInt =
    Mux(now < bound, id, Mux(activeAtNow, Constraint.TPPD_ACTIVE.U(8.W), Constraint.TPPD_IDLE.U(8.W)))

  private val ear1 = earliestFrom(bound1)
  private val ear2 = earliestFrom(bound2)
  private val legal1 = ear1 === now
  private val legal2 = ear2 === now

  // ---------------------------------------- state rules (waiting cannot fix)
  private val stateChecks: Seq[(Bool, Int)] = Seq(
    isUndef -> Constraint.PKT_UNDEFINED_OPCODE,
    (io.tckPs < p.tckMinPs.U) -> Constraint.CFG_TCK_RANGE,
    (isMrs && clReserved(mCl)) -> Constraint.MRS_CL_RESERVED,
    (isMrs && mFixed) -> Constraint.MRS_RESERVED_BIT,
    (isMrs && tck < clMinTck(mCl)) -> Constraint.MRS_CL_TCK,
    (isRef && refop(1)) -> Constraint.REF_REFOP_RESERVED,
    ((isPre || isRef) && bankMask === 0.U) -> Constraint.PKT_NO_BANK,
    (!everReset && !isReset) -> Constraint.INIT_RESET_REQUIRED,
    (needPrea && !(isReset || (isPre && bankMask.andR))) -> Constraint.INIT_PREA_REQUIRED,
    (!needPrea && needMrs && !(isReset || isMrs)) -> Constraint.INIT_MRS_REQUIRED,
    (everReset && !needPrea && !needMrs && needZqInit && !(isReset || isMrs || (isZq && zqop === 0.U))) ->
      Constraint.INIT_ZQINIT_REQUIRED,
    (utrMode && !(isRd || isUtr || isReset)) -> Constraint.UTR_MODE_CMD,
    (isAct && bankOpen(ba)) -> Constraint.ACT_BANK_ACTIVE,
    (columnAccess && !bankOpen(ba)) -> Constraint.RW_BANK_IDLE,
    (isPre && (bankMask & bankKnown.asUInt & ~bankOpen.asUInt).orR) -> Constraint.PRE_BANK_PRECHARGED,
    (isZq && anyOpen) -> Constraint.ZQ_REQUIRES_IDLE,
    (isUtr && anyOpen) -> Constraint.UTR_REQUIRES_IDLE,
    (isRd && mrZout === 0.U) -> Constraint.READ_ZOUT_OPEN
  )
  private val stateErr = stateChecks.map(_._1).reduce(_ || _)
  private val stateId = PriorityMux(stateChecks.map { case (c, id) => c -> id.U(8.W) } :+ (true.B -> 0.U(8.W)))

  // --------------------------------------------------------------- verdict
  private val selR2 = io.refreshSelect === 2.U
  private val collapse = io.refreshSelect === 1.U || selR2
  private val earSel = Mux(selR2, ear2, ear1)
  private val legalSel = Mux(selR2, legal2, legal1)
  private val idSel = Mux(selR2, failId(bound2, id2), failId(bound1, id1))

  private val kind = WireDefault(Kind.NONE.U(2.W))
  private val cid = WireDefault(Constraint.NONE.U(8.W))
  private val earliest = WireDefault(0.U(W.W))

  when(!io.valid) {
    kind := Kind.NONE.U
  }.elsewhen(stateErr) {
    kind := Kind.VIOLATION.U
    cid := stateId
  }.elsewhen(refPending && !collapse && legal1 =/= legal2) {
    // Legal under reading 1 only. Reading 2 is never shorter, so an offer
    // early under both readings falls through and reports reading 1.
    kind := Kind.INTERPRETATION.U
    cid := Mux(isPd, Constraint.UNMODELED_POWER_DOWN.U, Constraint.REFRESH_BUSY.U)
    earliest := Mux(isPd, 0.U, maxU(ear1, ear2))
  }.elsewhen(!legalSel) {
    kind := Kind.VIOLATION.U
    cid := idSel
    earliest := earSel
  }.elsewhen(isPd) {
    kind := Kind.INTERPRETATION.U
    cid := Constraint.UNMODELED_POWER_DOWN.U
  }.otherwise {
    kind := Kind.ACCEPT.U
  }

  io.accepted := kind === Kind.ACCEPT.U
  io.kind := kind
  io.constraintId := cid
  io.earliest := earliest
  io.opCode := op
  private val timingVisible = io.valid && !stateErr
  io.earliestRs1 := Mux(timingVisible, ear1, 0.U)
  io.earliestRs2 := Mux(timingVisible, ear2, 0.U)
  io.bank := ba
  io.row := Mux(isAct, actRow, openRow(ba))
  io.column := col
  io.words := words
  private val rl = p.additiveLatency.U +& clValue(mrCl)
  io.latency := rl

  // ---------------------------------------------------------------- commit
  private val commit = io.valid && !isPd && (kind === Kind.ACCEPT.U || kind === Kind.INTERPRETATION.U)
  private val newBurstEnd = now + rl + (words << log2Ceil(p.wordCk))

  when(commit) {
    havePrev := true.B
    prevAt := now
    refPending := false.B

    when(isReset) {
      everReset := true.B
      resetAt := now
      needPrea := true.B
      needMrs := true.B
      for (i <- 0 until 4) {
        bankOpen(i) := false.B
        bankKnown(i) := false.B
        actValid(i) := false.B
        preValid(i) := false.B
        wrValid(i) := false.B
      }
      actAnyValid := false.B
      burstValid := false.B
      modeValid := false.B
      zqValid := false.B
      utrMode := false.B
      mrCl := 0.U
      mrNwr := 3.U
      mrZout := 0.U
      mrOdt := 0.U
      mrStbOdt := false.B
      mrCsrfx := false.B
      mrOdtPd := false.B
    }
    when(isPre) {
      for (i <- 0 until 4) {
        when(bankMask(i)) {
          bankOpen(i) := false.B
          bankKnown(i) := true.B
          preValid(i) := true.B
          preAt(i) := now
        }
      }
      needPrea := false.B
    }
    when(isAct) {
      bankOpen(ba) := true.B
      bankKnown(ba) := true.B
      openRow(ba) := actRow
      actValid(ba) := true.B
      actAt(ba) := now
      actAnyValid := true.B
      actAnyAt := now
    }
    when(isRd || isWr) {
      burstValid := true.B
      burstWrite := isWr
      burstEnd := newBurstEnd
    }
    when(isWr) {
      wrValid(ba) := true.B
      wrEndAt(ba) := newBurstEnd
    }
    when(isMrs) {
      mrCl := mCl
      mrNwr := mNwr
      mrZout := mZout
      mrOdt := mOdt
      mrStbOdt := mStbOdt
      mrCsrfx := mCsrfx
      mrOdtPd := mOdtPd
      modeValid := true.B
      modeWasMrs := true.B
      modeAt := now
      needMrs := false.B
    }
    when(isUtr) {
      utrMode := utrEn
      utrOpR := utrOp
      modeValid := true.B
      modeWasMrs := false.B
      modeAt := now
    }
    when(isZq) {
      zqValid := true.B
      zqAt := now
      zqOpR := zqop
      when(zqop === 0.U) { needZqInit := false.B }
    }
    when(isRef) {
      for (i <- 0 until 4) {
        bankOpen(i) := false.B
        bankKnown(i) := true.B
      }
      refPending := true.B
      refAt := now
      refBanks := PopCount(bankMask)
      refLp := refop(0)
      refLoop := mrCsrfx
    }
  }
}
