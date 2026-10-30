package midas
package models

import chisel3._
import chisel3.util._

import org.chipsalliance.cde.config.Parameters

import junctions.NastiKey

import firesim.lib.nasti._

/** Independent EM6GA16L timing model.
  *
  * Command minima are the speed-1600 column of Etron Rev. 1.4 Table 11-3.
  * The host address fields are the linear packing of a 32-byte word, a
  * 6-bit column, a 12-bit row, and a 2-bit bank. The datasheet does not
  * define a CPU address map.
  *
  * One-shot refresh uses the Section 5 row-step reading when refRowStep is
  * set: stall = nRefRows * tRefStep * nRefBanks. The alternate one-tREFI
  * reading is refRowStep = 0. There is no tRFC symbol in the datasheet.
  * The first refresh is at tRefInterval, not at cycle 0. tRefInterval = 0
  * disables refresh.
  *
  * This scheduler waits until a command is legal. It is not the ETH
  * command checker. An early controller command is not retimed here.
  */
case class IndRpcDramModelConfig(
  params:       BaseParams,
  requestTrace: Boolean = false,
) extends BaseConfig {
  def elaborate()(implicit p: Parameters): IndRpcDramModel = Module(new IndRpcDramModel(this))
}

class IndRpcDramMMRegIO(cfg: IndRpcDramModelConfig)(implicit p: Parameters) extends SplitTransactionMMRegIO(cfg) {
  val bankAddr = Input(new ProgrammableSubAddr(maskBits = 2, longName = "RPC Bank", defaultOffset = 23, defaultMask = 3))
  val rowAddr  = Input(new ProgrammableSubAddr(maskBits = 12, longName = "RPC Row", defaultOffset = 11, defaultMask = 4095))
  val colAddr  = Input(new ProgrammableSubAddr(maskBits = 6, longName = "RPC Column group", defaultOffset = 5, defaultMask = 63))

  val tRCD       = Input(UInt(16.W))
  val tRP        = Input(UInt(16.W))
  val tRAS       = Input(UInt(16.W))
  val tRC        = Input(UInt(16.W))
  val tRRD       = Input(UInt(16.W))
  val tWR        = Input(UInt(16.W))
  val tPPDidle   = Input(UInt(16.W))
  val tPPDact    = Input(UInt(16.W))
  val rl         = Input(UInt(16.W))
  val ckPerWord  = Input(UInt(16.W))
  val wordBytes  = Input(UInt(16.W))
  val openPage      = Input(Bool())
  val tRefInterval  = Input(UInt(32.W))
  val tRefStep      = Input(UInt(16.W))
  val nRefRows      = Input(UInt(16.W))
  val nRefBanks     = Input(UInt(4.W))
  val refRowStep    = Input(Bool())
  val refreshCount  = Output(UInt(32.W))

  val registers = maxReqRegisters ++ Seq(
    tRCD         -> RuntimeSetting(11, "ACT to RD/WR (tRCD), speed-1600"),
    tRP          -> RuntimeSetting(11, "PRE to ACT (tRP)"),
    tRAS         -> RuntimeSetting(28, "ACT to PRE (tRAS)"),
    tRC          -> RuntimeSetting(39, "ACT to ACT same bank (tRC)"),
    tRRD         -> RuntimeSetting(6, "ACT to ACT different bank (tRRD)"),
    tWR          -> RuntimeSetting(12, "Write recovery before PRE (tWR)"),
    tPPDidle     -> RuntimeSetting(4, "Parallel command spacing, all banks precharged"),
    tPPDact      -> RuntimeSetting(8, "Parallel command spacing, a row is open"),
    rl           -> RuntimeSetting(12, "RL = WL = AL + CL, AL=1, CL=11"),
    ckPerWord    -> RuntimeSetting(8, "CK per 32-byte word"),
    wordBytes    -> RuntimeSetting(32, "Bytes in one RPC word"),
    openPage     -> RuntimeSetting(1, "1 keeps the row open, 0 precharges after the burst"),
    tRefInterval -> RuntimeSetting(0, "Cycles from reset to the first refresh, and between refreshes. 0 disables."),
    tRefStep     -> RuntimeSetting(80, "tREFI in CK. FST 100 ns at 1.25 ns."),
    nRefRows     -> RuntimeSetting(4096, "Rows walked by one one-shot refresh"),
    nRefBanks    -> RuntimeSetting(4, "Banks in the one-shot refresh"),
    refRowStep   -> RuntimeSetting(1, "1 = rows*tREFI*banks, 0 = one tREFI"),
  )

  def requestSettings(): Unit = {
    Console.println("Generating a runtime configuration for RPC DRAM")
  }
}

class IndRpcDramModelIO(val cfg: IndRpcDramModelConfig)(implicit p: Parameters) extends SplitTransactionModelIO()(p) {
  val mmReg = new IndRpcDramMMRegIO(cfg)
}

class IndRpcDramQueueEntry(nastiParams: NastiParameters) extends Bundle {
  val xaction = new TransactionMetaData(nastiParams)
  val addr    = UInt(nastiParams.addrBits.W)
}

class IndRpcDramPending(nastiParams: NastiParameters) extends Bundle {
  val xaction = new TransactionMetaData(nastiParams)
  val release = UInt(64.W)
}

class IndRpcDramModel(cfg: IndRpcDramModelConfig)(implicit p: Parameters) extends SplitTransactionModel(cfg)(p) {
  val longName = "RPC DRAM bank timing model"
  def printTimingModelGenerationConfig: Unit = {}

  lazy val io = IO(new IndRpcDramModelIO(cfg))

  val nBanks    = 4
  val beatBytes = (p(NastiKey).dataBits / 8).U

  val readQ  = Module(new Queue(new IndRpcDramQueueEntry(p(NastiKey)), cfg.maxReads))
  val writeQ = Module(new Queue(new IndRpcDramQueueEntry(p(NastiKey)), cfg.maxWrites))
  readQ.io.enq.valid        := tNasti.ar.fire
  readQ.io.enq.bits.xaction := TransactionMetaData(p(NastiKey), tNasti.ar.bits)
  readQ.io.enq.bits.addr    := tNasti.ar.bits.addr
  writeQ.io.enq.valid        := newWReq
  writeQ.io.enq.bits.xaction := TransactionMetaData(p(NastiKey), awQueue.io.deq.bits)
  writeQ.io.enq.bits.addr    := awQueue.io.deq.bits.addr
  assert(readQ.io.enq.ready || !tNasti.ar.fire, "RPC read ingress overflow")
  assert(writeQ.io.enq.ready || !newWReq, "RPC write ingress overflow")

  val preferWrite = RegInit(false.B)
  val takeWrite   = writeQ.io.deq.valid && (!readQ.io.deq.valid || preferWrite)
  val takeRead    = readQ.io.deq.valid && !takeWrite
  val head        = Wire(new IndRpcDramQueueEntry(p(NastiKey)))
  head := Mux(takeWrite, writeQ.io.deq.bits, readQ.io.deq.bits)
  val headValid = takeWrite || takeRead

  val rowOpen  = RegInit(VecInit(Seq.fill(nBanks)(false.B)))
  val openRow  = Reg(Vec(nBanks, UInt(12.W)))
  val actCycle = Reg(Vec(nBanks, UInt(64.W)))
  val actOk    = RegInit(VecInit(Seq.fill(nBanks)(0.U(64.W))))
  val preOk    = RegInit(VecInit(Seq.fill(nBanks)(0.U(64.W))))
  val lastAct  = RegInit(0.U(64.W))
  val lastParallel = RegInit(0.U(64.W))
  val cmdFree  = RegInit(0.U(64.W))
  val dataFree = RegInit(0.U(64.W))
  val anyOpen  = rowOpen.reduce(_ || _)

  val sIdle :: sPre :: sAct :: sCas :: sData :: sClose :: sRef :: Nil = Enum(7)
  val state = RegInit(sIdle)

  val hold      = Reg(new IndRpcDramQueueEntry(p(NastiKey)))
  val holdWrite = Reg(Bool())
  val holdBank  = Reg(UInt(2.W))
  val holdRow   = Reg(UInt(12.W))
  val holdBurst = Reg(UInt(16.W))
  val cmdAt     = Reg(UInt(64.W))
  val refreshes = RegInit(0.U(32.W))
  val nextRef   = RegInit(0.U(64.W))
  val refArmed  = RegInit(false.B)
  io.mmReg.refreshCount := refreshes
  val refStep  = io.mmReg.tRefStep.pad(32)
  val refRows  = io.mmReg.nRefRows.pad(32)
  val refBanks = Mux(io.mmReg.nRefBanks === 0.U, 1.U, io.mmReg.nRefBanks).pad(32)
  val refStall = Mux(io.mmReg.refRowStep, (refRows * refStep) * refBanks, refStep)

  val pending = Module(new Queue(new IndRpcDramPending(p(NastiKey)), cfg.maxReads + cfg.maxWrites, flow = true))

  def max2(a: UInt, b: UInt): UInt = Mux(a > b, a, b)
  def tPPD: UInt = Mux(anyOpen, io.mmReg.tPPDact, io.mmReg.tPPDidle)
  // Section 2.8 and Table 11-3: in activate state, successive parallel
  // commands are separated by 8 CK or an integer multiple. This is a phase
  // constraint in addition to the tRCD/tRAS/tWR minima.
  def activeSlot(candidate: UInt, anchor: UInt, active: Bool): UInt = {
    val rounded = ((candidate - anchor + 7.U) >> 3) << 3
    Mux(active, anchor + rounded, candidate)
  }
  def onActiveSlot(now: UInt): Bool = !anyOpen || ((now - lastParallel) % 8.U === 0.U)

  val headBank = io.mmReg.bankAddr.getSubAddr(head.addr)
  val headRow  = io.mmReg.rowAddr.getSubAddr(head.addr)
  val nbytes   = (head.xaction.len + 1.U) * beatBytes
  val wb       = Mux(io.mmReg.wordBytes === 0.U, 1.U, io.mmReg.wordBytes).pad(nbytes.getWidth)
  val nWords   = (nbytes + wb - 1.U) / wb
  val burstCk  = nWords * io.mmReg.ckPerWord

  def casReady(bank: UInt, now: UInt): UInt = {
    val bus = Mux(dataFree > io.mmReg.rl, dataFree - io.mmReg.rl, 0.U)
    max2(max2(max2(now, actCycle(bank) + io.mmReg.tRCD), cmdFree), bus)
  }
  val refBankReady = (0 until nBanks)
    .map(i => Mux(rowOpen(i), max2(actOk(i), preOk(i)), 0.U(64.W)))
    .reduce(max2)
  val refReady = max2(max2(refBankReady, dataFree), cmdFree)

  readQ.io.deq.ready   := false.B
  writeQ.io.deq.ready  := false.B
  pending.io.enq.valid := false.B
  pending.io.enq.bits.xaction := hold.xaction
  pending.io.enq.bits.release := tCycle - egressUnitDelay.U

  switch(state) {
    is(sIdle) {
      when(io.mmReg.tRefInterval =/= 0.U && !refArmed) {
        nextRef  := io.mmReg.tRefInterval.pad(64)
        refArmed := true.B
      }.elsewhen(io.mmReg.tRefInterval =/= 0.U && refArmed && tCycle >= nextRef) {
        when(tCycle >= refReady && onActiveSlot(tCycle)) {
          val stall = refStall.pad(64)
          state     := sRef
          cmdAt     := tCycle + stall
          refreshes := refreshes + 1.U
          nextRef   := tCycle + io.mmReg.tRefInterval.pad(64) + stall
          lastParallel := tCycle
          cmdFree := tCycle + io.mmReg.tPPDidle
          rowOpen.foreach(_ := false.B)
          if (cfg.requestTrace) {
            printf("INDREF,%d,%d\n", tCycle, refStall)
          }
        }
      }.elsewhen(headValid && pending.io.enq.ready) {
        hold      := head
        holdWrite := head.xaction.isWrite
        holdBank  := headBank
        holdRow   := headRow
        holdBurst := burstCk
        when(rowOpen(headBank) && openRow(headBank) === headRow) {
          state := sCas
          cmdAt := activeSlot(casReady(headBank, tCycle), lastParallel, anyOpen)
        }.elsewhen(rowOpen(headBank)) {
          state := sPre
          cmdAt := activeSlot(max2(max2(tCycle, preOk(headBank)), cmdFree), lastParallel, anyOpen)
        }.otherwise {
          state := sAct
          cmdAt := activeSlot(max2(max2(max2(tCycle, actOk(headBank)), lastAct + io.mmReg.tRRD), cmdFree), lastParallel, anyOpen)
        }
      }
    }
    is(sPre) {
      when(tCycle >= cmdAt) {
        rowOpen(holdBank) := false.B
        lastParallel      := tCycle
        actOk(holdBank)   := tCycle + io.mmReg.tRP
        cmdFree           := tCycle + tPPD
        state             := sAct
        val otherOpen = (0 until nBanks).map(i => rowOpen(i) && holdBank =/= i.U).reduce(_ || _)
        val ready = max2(tCycle + io.mmReg.tRP, max2(tCycle + tPPD, lastAct + io.mmReg.tRRD))
        cmdAt             := activeSlot(ready, tCycle, otherOpen)
        if (cfg.requestTrace) {
          printf("INDCMD,%d,2,%d,%d\n", tCycle, holdBank, holdRow)
        }
      }
    }
    is(sAct) {
      when(tCycle >= cmdAt) {
        rowOpen(holdBank)  := true.B
        openRow(holdBank)  := holdRow
        actCycle(holdBank) := tCycle
        preOk(holdBank)    := tCycle + io.mmReg.tRAS
        actOk(holdBank)    := tCycle + io.mmReg.tRC
        lastAct            := tCycle
        lastParallel       := tCycle
        cmdFree            := tCycle + io.mmReg.tPPDact
        state              := sCas
        cmdAt              := activeSlot(max2(tCycle + io.mmReg.tRCD, tCycle + io.mmReg.tPPDact), tCycle, true.B)
        if (cfg.requestTrace) {
          printf("INDCMD,%d,1,%d,%d\n", tCycle, holdBank, holdRow)
        }
      }
    }
    is(sCas) {
      when(tCycle >= cmdAt && pending.io.enq.ready && onActiveSlot(tCycle)) {
        val doneCycle = tCycle + io.mmReg.rl + holdBurst
        dataFree := doneCycle
        lastParallel := tCycle
        // The next column command waits until this burst's clocks have
        // elapsed (Section 2.4). An earlier column would violate tCCD.
        cmdFree := tCycle + holdBurst
        when(hold.xaction.isWrite) {
          preOk(holdBank) := max2(preOk(holdBank), doneCycle + io.mmReg.tWR)
        }.otherwise {
          preOk(holdBank) := max2(preOk(holdBank), doneCycle)
        }
        pending.io.enq.valid        := true.B
        pending.io.enq.bits.release := doneCycle - egressUnitDelay.U
        readQ.io.deq.ready          := !holdWrite
        writeQ.io.deq.ready         := holdWrite
        preferWrite                 := !preferWrite
        if (cfg.requestTrace) {
          printf(
            "INDCMD,%d,%d,%d,%d\n",
            tCycle,
            Mux(hold.xaction.isWrite, 4.U, 3.U),
            holdBank,
            holdRow,
          )
        }
        when(io.mmReg.openPage) {
          state := sIdle
        }.otherwise {
          state := sData
          cmdAt := doneCycle
        }
      }
    }
    is(sData) {
      // Closed page only. The response was posted and the request popped in sCas.
      when(tCycle >= cmdAt) {
        state := sClose
        cmdAt := activeSlot(max2(tCycle, preOk(holdBank)), lastParallel, anyOpen)
      }
    }
    is(sClose) {
      when(tCycle >= cmdAt) {
        rowOpen(holdBank) := false.B
        lastParallel      := tCycle
        actOk(holdBank)   := tCycle + io.mmReg.tRP
        cmdFree           := tCycle + tPPD
        state             := sIdle
        if (cfg.requestTrace) {
          printf("INDCMD,%d,2,%d,%d\n", tCycle, holdBank, holdRow)
        }
      }
    }
    is(sRef) {
      when(tCycle >= cmdAt) {
        state := sIdle
      }
    }
  }

  val readyResp = pending.io.deq.valid && pending.io.deq.bits.release <= tCycle
  pending.io.deq.ready := readyResp && Mux(pending.io.deq.bits.xaction.isWrite, wResp.ready, rResp.ready)
  rResp.valid := readyResp && !pending.io.deq.bits.xaction.isWrite
  wResp.valid := readyResp && pending.io.deq.bits.xaction.isWrite
  rResp.bits  := ReadResponseMetaData(p(NastiKey), pending.io.deq.bits.xaction)
  wResp.bits  := WriteResponseMetaData(p(NastiKey), pending.io.deq.bits.xaction)
}
