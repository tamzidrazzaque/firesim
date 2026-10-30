package midas
package models

import scala.Console.{RESET, UNDERLINED}

import chisel3._
import chisel3.util._

import org.chipsalliance.cde.config.Parameters

import junctions.NastiKey

import firesim.lib.nasti._

/** FASED timing model for one HyperRAM device.
  *
  * This is the SoC-facing AXI timing model. It does not drive DQ or RWDS.
  * Functional bytes stay in the normal FASED memory, the same split the HBM
  * model uses. The Python device in ``memperiph.hyperram`` is the reference
  * for data, register state, and the refresh-debt integral. The Chisel model
  * reproduces the host-visible costs: CA, initial latency, optional fixed or
  * periodic extra latency, the data beat, tCSHI / tRWR, and tCSM splitting.
  *
  * Defaults match a 200 MHz S80KS2562-class part with the power-on fixed
  * latency of 7 CK (14 CK after doubling). All of those are runtime
  * registers, in memory-controller clocks.
  */
case class HyperRAMModelConfig(
  params:       BaseParams,
  requestTrace: Boolean = false,
) extends BaseConfig {
  def elaborate()(implicit p: Parameters): HyperRAMModel = Module(new HyperRAMModel(this))
}

class HyperRAMMMRegIO(cfg: HyperRAMModelConfig)(implicit p: Parameters) extends SplitTransactionMMRegIO(cfg) {
  val tCA            = Input(UInt(16.W))
  val tLAT           = Input(UInt(16.W))
  val tCSHI          = Input(UInt(16.W))
  val tRWR           = Input(UInt(16.W))
  val tCSM           = Input(UInt(16.W))
  val bytesPerCk     = Input(UInt(8.W))
  val fixedLatency   = Input(Bool())
  val refreshPeriod  = Input(UInt(32.W))
  val rowBytes       = Input(UInt(16.W))
  val extraLatencyEvents = Output(UInt(32.W))

  val registers = maxReqRegisters ++ Seq(
    tCA           -> RuntimeSetting(3, "HyperBus command/address clocks"),
    tLAT          -> RuntimeSetting(7, "Base initial latency (CK), before doubling"),
    tCSHI         -> RuntimeSetting(2, "Minimum CS# high, same direction (CK)"),
    tRWR          -> RuntimeSetting(7, "Read-to-write CS# high (CK)"),
    tCSM          -> RuntimeSetting(800, "Maximum CS# low (CK); longer AXI bursts are split"),
    bytesPerCk    -> RuntimeSetting(2, "Bytes transferred per CK during the data phase"),
    fixedLatency  -> RuntimeSetting(1, "1 = always 2x latency (CR0 fixed), 0 = variable"),
    refreshPeriod -> RuntimeSetting(800, "Assumed variable-latency collision phase (CK); 0 disables"),
    rowBytes      -> RuntimeSetting(1024, "Row size used only by the request trace"),
  )

  def requestSettings(): Unit = {
    Console.println(s"${UNDERLINED}Generating a runtime configuration for HyperRAM${RESET}")
  }
}

class HyperRAMModelIO(val cfg: HyperRAMModelConfig)(implicit p: Parameters) extends SplitTransactionModelIO()(p) {
  val mmReg = new HyperRAMMMRegIO(cfg)
}

class HyperRAMQueueEntry(nastiParams: NastiParameters) extends Bundle {
  val xaction = new TransactionMetaData(nastiParams)
  val addr    = UInt(nastiParams.addrBits.W)
}

class HyperRAMPending(nastiParams: NastiParameters) extends Bundle {
  val xaction    = new TransactionMetaData(nastiParams)
  val release    = UInt(64.W)
  val start      = UInt(64.W)
  val latencyCk  = UInt(16.W)
  val extra      = Bool()
  val addr       = UInt(nastiParams.addrBits.W)
}

class HyperRAMModel(cfg: HyperRAMModelConfig)(implicit p: Parameters) extends SplitTransactionModel(cfg)(p) {
  val longName = "HyperRAM transaction timing model"
  def printTimingModelGenerationConfig: Unit = {}

  lazy val io = IO(new HyperRAMModelIO(cfg))

  val beatBytes = (p(NastiKey).dataBits / 8).U

  // Separate queues so a read and a write that fire on the same cycle are
  // both captured. A one-hot arbiter into a single queue drops one of them
  // and the fuzzer never sees that response.
  val readQ  = Module(new Queue(new HyperRAMQueueEntry(p(NastiKey)), cfg.maxReads))
  val writeQ = Module(new Queue(new HyperRAMQueueEntry(p(NastiKey)), cfg.maxWrites))
  readQ.io.enq.valid        := tNasti.ar.fire
  readQ.io.enq.bits.xaction := TransactionMetaData(p(NastiKey), tNasti.ar.bits)
  readQ.io.enq.bits.addr    := tNasti.ar.bits.addr
  writeQ.io.enq.valid        := newWReq
  writeQ.io.enq.bits.xaction := TransactionMetaData(p(NastiKey), awQueue.io.deq.bits)
  writeQ.io.enq.bits.addr    := awQueue.io.deq.bits.addr
  assert(readQ.io.enq.ready || !tNasti.ar.fire, "HyperRAM read ingress overflow")
  assert(writeQ.io.enq.ready || !newWReq, "HyperRAM write ingress overflow")

  val preferWrite = RegInit(false.B)
  val takeWrite   = writeQ.io.deq.valid && (!readQ.io.deq.valid || preferWrite)
  val takeRead    = readQ.io.deq.valid && !takeWrite
  val issueBits   = Wire(new HyperRAMQueueEntry(p(NastiKey)))
  issueBits := Mux(takeWrite, writeQ.io.deq.bits, readQ.io.deq.bits)
  val issueValid = takeWrite || takeRead

  val csRise     = RegInit(0.U(64.W))
  val lastWrite  = RegInit(false.B)
  val haveLast   = RegInit(false.B)
  val refreshAge = RegInit(0.U(32.W))
  val extraCount = RegInit(0.U(32.W))
  io.mmReg.extraLatencyEvents := extraCount

  val pending = Module(new Queue(new HyperRAMPending(p(NastiKey)), cfg.maxReads + cfg.maxWrites, flow = true))

  val nbytes = (issueBits.xaction.len + 1.U) * beatBytes
  // Verilator -Wall rejects a divisor narrower than the dividend.
  val bpc    = Mux(io.mmReg.bytesPerCk === 0.U, 1.U, io.mmReg.bytesPerCk).pad(nbytes.getWidth)
  val dataCk = (nbytes + bpc - 1.U) / bpc
  val collide = io.mmReg.refreshPeriod =/= 0.U && refreshAge >= io.mmReg.refreshPeriod
  val doubled = io.mmReg.fixedLatency || collide
  val lat     = Mux(doubled, io.mmReg.tLAT << 1, io.mmReg.tLAT)
  val overhead = io.mmReg.tCA + lat
  val room = Mux(io.mmReg.tCSM > overhead, io.mmReg.tCSM - overhead, 1.U)
  val chunks = Mux(dataCk <= room, 1.U, (dataCk + room - 1.U) / room)
  val dirChange = haveLast && !lastWrite && issueBits.xaction.isWrite
  val gap = Mux(dirChange, Mux(io.mmReg.tRWR > io.mmReg.tCSHI, io.mmReg.tRWR, io.mmReg.tCSHI), io.mmReg.tCSHI)
  // Gap is known only once this command's direction is known, so the
  // previous command records when CS# rose and this command waits tCSHI
  // or tRWR from that edge.
  val earliest = csRise + gap
  val canIssue = issueValid && tCycle >= earliest && pending.io.enq.ready
  readQ.io.deq.ready  := canIssue && takeRead
  writeQ.io.deq.ready := canIssue && takeWrite
  when(canIssue) { preferWrite := !preferWrite }
  pending.io.enq.valid := canIssue
  // Each extra chip-select repeats CA + latency + the turnaround gap.
  val splitTax = (chunks - 1.U) * (overhead + gap)
  val csLow    = overhead + dataCk + splitTax
  val done     = tCycle + csLow

  pending.io.enq.bits.xaction   := issueBits.xaction
  pending.io.enq.bits.release   := done - egressUnitDelay.U
  pending.io.enq.bits.start     := tCycle
  pending.io.enq.bits.latencyCk := lat
  pending.io.enq.bits.extra     := doubled
  pending.io.enq.bits.addr      := issueBits.addr

  when(canIssue) {
    csRise     := done
    lastWrite  := issueBits.xaction.isWrite
    haveLast   := true.B
    refreshAge := Mux(collide, 0.U, refreshAge + csLow)
    when(collide) { extraCount := extraCount + 1.U }
  }.elsewhen(refreshAge =/= ~(0.U(32.W))) {
    refreshAge := refreshAge + 1.U
  }

  if (cfg.requestTrace) {
    when(canIssue) {
      val rowDiv = Mux(io.mmReg.rowBytes === 0.U, 1.U, io.mmReg.rowBytes)
        .pad(issueBits.addr.getWidth)
      val row = issueBits.addr / rowDiv
      printf(
        "HYPERREQ,%d,%d,%x,%d,%d,%d,%d,%x\n",
        tCycle,
        issueBits.xaction.isWrite,
        issueBits.addr,
        issueBits.xaction.id,
        issueBits.xaction.len,
        lat,
        doubled,
        row,
      )
    }
  }

  val readyResp = pending.io.deq.valid && pending.io.deq.bits.release <= tCycle
  pending.io.deq.ready := readyResp && Mux(pending.io.deq.bits.xaction.isWrite, wResp.ready, rResp.ready)
  rResp.valid := readyResp && !pending.io.deq.bits.xaction.isWrite
  wResp.valid := readyResp && pending.io.deq.bits.xaction.isWrite
  rResp.bits  := ReadResponseMetaData(p(NastiKey), pending.io.deq.bits.xaction)
  wResp.bits  := WriteResponseMetaData(p(NastiKey), pending.io.deq.bits.xaction)

  assert(pending.io.enq.ready || !canIssue, "HyperRAM completion pipe overflow")
}
