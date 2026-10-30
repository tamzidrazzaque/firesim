package midas
package models

import chisel3._
import chisel3.util._

import org.chipsalliance.cde.config.Parameters

import junctions.NastiKey

import firesim.lib.nasti._

/** FASED timing model for one RPC DRAM device.
  *
  * One AXI port, four banks, open- or closed-page. The scheduler issues at
  * most one command (ACT, PRE, CAS) per cycle and enforces tRCD, tRP, tRAS,
  * tRC, tRRD, tPPD, and the data-bus occupancy of a BL16 word. It does not
  * implement the serial address-streaming pipeline; that lives in the Python
  * reference (``memperiph.rpcdram``), which is the model used for the
  * bandwidth numbers. This module is the FireSim integration point: same
  * address map as the ETH controller, runtime-programmable timings, and a
  * request trace.
  *
  * Defaults are the speed-1600 column (tCK = 1.25 ns, CL = 11, RL = 12)
  * expressed in controller clocks. A 200 MHz ETH PHY profile is a different
  * plusarg file, not a different bitstream.
  */
case class RpcDramModelConfig(
  params:       BaseParams,
  requestTrace: Boolean = false,
) extends BaseConfig {
  def elaborate()(implicit p: Parameters): RpcDramModel = Module(new RpcDramModel(this))
}

class RpcDramMMRegIO(cfg: RpcDramModelConfig)(implicit p: Parameters) extends SplitTransactionMMRegIO(cfg) {
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
  val openPage   = Input(Bool())
  val tREFI      = Input(UInt(32.W))
  val tRFC       = Input(UInt(32.W))
  val refreshCount = Output(UInt(32.W))

  val registers = maxReqRegisters ++ Seq(
    tRCD      -> RuntimeSetting(11, "ACT to RD/WR (tRCD), speed-1600"),
    tRP       -> RuntimeSetting(11, "PRE to ACT (tRP)"),
    tRAS      -> RuntimeSetting(28, "ACT to PRE (tRAS)"),
    tRC       -> RuntimeSetting(39, "ACT to ACT same bank (tRC)"),
    tRRD      -> RuntimeSetting(6, "ACT to ACT different bank (tRRD)"),
    tWR       -> RuntimeSetting(12, "Write recovery before PRE (tWR)"),
    tPPDidle  -> RuntimeSetting(4, "Parallel command spacing, all banks precharged"),
    tPPDact   -> RuntimeSetting(8, "Parallel command spacing, a row is open"),
    rl        -> RuntimeSetting(12, "Read and write latency RL = WL = CL + 1"),
    ckPerWord -> RuntimeSetting(8, "CK per 32-byte RPC word"),
    wordBytes -> RuntimeSetting(32, "Bytes in one RPC word"),
    openPage  -> RuntimeSetting(1, "1 = open page, 0 = closed page (ETH-style)"),
    tREFI     -> RuntimeSetting(0, "Cycles between refresh stalls; 0 disables"),
    tRFC      -> RuntimeSetting(1310720, "Refresh stall (CK). Default is 4-bank FST."),
  )

  def requestSettings(): Unit = {
    Console.println("Generating a runtime configuration for RPC DRAM")
  }
}

class RpcDramModelIO(val cfg: RpcDramModelConfig)(implicit p: Parameters) extends SplitTransactionModelIO()(p) {
  val mmReg = new RpcDramMMRegIO(cfg)
}

class RpcDramQueueEntry(nastiParams: NastiParameters) extends Bundle {
  val xaction = new TransactionMetaData(nastiParams)
  val addr    = UInt(nastiParams.addrBits.W)
}

class RpcDramPending(nastiParams: NastiParameters) extends Bundle {
  val xaction = new TransactionMetaData(nastiParams)
  val release = UInt(64.W)
}

class RpcDramModel(cfg: RpcDramModelConfig)(implicit p: Parameters) extends SplitTransactionModel(cfg)(p) {
  val longName = "RPC DRAM bank timing model"
  def printTimingModelGenerationConfig: Unit = {}

  lazy val io = IO(new RpcDramModelIO(cfg))

  val nBanks    = 4
  val beatBytes = (p(NastiKey).dataBits / 8).U

  val readQ  = Module(new Queue(new RpcDramQueueEntry(p(NastiKey)), cfg.maxReads))
  val writeQ = Module(new Queue(new RpcDramQueueEntry(p(NastiKey)), cfg.maxWrites))
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
  val head        = Wire(new RpcDramQueueEntry(p(NastiKey)))
  head := Mux(takeWrite, writeQ.io.deq.bits, readQ.io.deq.bits)
  val headValid = takeWrite || takeRead

  val rowOpen  = RegInit(VecInit(Seq.fill(nBanks)(false.B)))
  val openRow  = Reg(Vec(nBanks, UInt(12.W)))
  val actCycle = Reg(Vec(nBanks, UInt(64.W)))
  val actOk    = RegInit(VecInit(Seq.fill(nBanks)(0.U(64.W))))
  val preOk    = RegInit(VecInit(Seq.fill(nBanks)(0.U(64.W))))
  val lastAct  = RegInit(0.U(64.W))
  val cmdFree  = RegInit(0.U(64.W))
  val dataFree = RegInit(0.U(64.W))
  val anyOpen  = rowOpen.reduce(_ || _)

  val sIdle :: sPre :: sAct :: sCas :: sData :: sClose :: sRef :: Nil = Enum(7)
  val state = RegInit(sIdle)

  val hold      = Reg(new RpcDramQueueEntry(p(NastiKey)))
  val holdWrite = Reg(Bool())
  val holdBank  = Reg(UInt(2.W))
  val holdRow   = Reg(UInt(12.W))
  val holdBurst = Reg(UInt(16.W))
  val cmdAt     = Reg(UInt(64.W))
  val refreshes = RegInit(0.U(32.W))
  val nextRef   = RegInit(0.U(64.W))
  io.mmReg.refreshCount := refreshes

  val pending = Module(new Queue(new RpcDramPending(p(NastiKey)), cfg.maxReads + cfg.maxWrites, flow = true))

  def max2(a: UInt, b: UInt): UInt = Mux(a > b, a, b)
  def tPPD: UInt = Mux(anyOpen, io.mmReg.tPPDact, io.mmReg.tPPDidle)

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

  readQ.io.deq.ready   := false.B
  writeQ.io.deq.ready  := false.B
  pending.io.enq.valid := false.B
  pending.io.enq.bits.xaction := hold.xaction
  pending.io.enq.bits.release := tCycle - egressUnitDelay.U

  switch(state) {
    is(sIdle) {
      when(io.mmReg.tREFI =/= 0.U && tCycle >= nextRef) {
        state     := sRef
        cmdAt     := tCycle + io.mmReg.tRFC
        refreshes := refreshes + 1.U
        nextRef   := tCycle + io.mmReg.tREFI + io.mmReg.tRFC
        rowOpen.foreach(_ := false.B)
        if (cfg.requestTrace) {
          printf("RPCREF,%d,%d\n", tCycle, io.mmReg.tRFC)
        }
      }.elsewhen(headValid && pending.io.enq.ready) {
        hold      := head
        holdWrite := head.xaction.isWrite
        holdBank  := headBank
        holdRow   := headRow
        holdBurst := burstCk
        when(rowOpen(headBank) && openRow(headBank) === headRow) {
          state := sCas
          cmdAt := casReady(headBank, tCycle)
        }.elsewhen(rowOpen(headBank)) {
          state := sPre
          cmdAt := max2(max2(tCycle, preOk(headBank)), cmdFree)
        }.otherwise {
          state := sAct
          cmdAt := max2(max2(max2(tCycle, actOk(headBank)), lastAct + io.mmReg.tRRD), cmdFree)
        }
      }
    }
    is(sPre) {
      when(tCycle >= cmdAt) {
        rowOpen(holdBank) := false.B
        actOk(holdBank)   := tCycle + io.mmReg.tRP
        cmdFree           := tCycle + tPPD
        state             := sAct
        cmdAt             := max2(tCycle + io.mmReg.tRP, max2(tCycle + tPPD, lastAct + io.mmReg.tRRD))
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
        cmdFree            := tCycle + io.mmReg.tPPDact
        state              := sCas
        cmdAt              := max2(tCycle + io.mmReg.tRCD, tCycle + io.mmReg.tPPDact)
      }
    }
    is(sCas) {
      when(tCycle >= cmdAt && pending.io.enq.ready) {
        val doneCycle = tCycle + io.mmReg.rl + holdBurst
        dataFree := doneCycle
        // Open page: the next column command may be a serial continuation
        // one word-time later, overlapping the data burst. Closed page keeps
        // the command bus until this burst ends, then precharges.
        cmdFree := tCycle + Mux(io.mmReg.openPage, io.mmReg.ckPerWord, tPPD)
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
            "RPCREQ,%d,%d,%x,%d,%d,%d,%x\n",
            tCycle,
            hold.xaction.isWrite,
            hold.addr,
            hold.xaction.id,
            hold.xaction.len,
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
        cmdAt := max2(tCycle, preOk(holdBank))
      }
    }
    is(sClose) {
      when(tCycle >= cmdAt) {
        rowOpen(holdBank) := false.B
        actOk(holdBank)   := tCycle + io.mmReg.tRP
        cmdFree           := tCycle + tPPD
        state             := sIdle
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
