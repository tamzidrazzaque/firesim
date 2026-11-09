// See LICENSE for license details.
package midas
package models

import Console.{RESET, UNDERLINED}

import chisel3._
import chisel3.util._

import org.chipsalliance.cde.config.Parameters

import junctions.NastiKey

/** Byte-addressable technology-spec timing model.
  *
  * This is not a DRAM. It does not issue ACT/PRE/RD/WR/REF and it does not
  * share scheduler state with [[HBMModel]] or [[FirstReadyFCFSModel]].
  *
  * The cycle rules match `sim/scripts/emerging-memory/techspec.py`:
  *
  * 1. A read is admitted on AR fire. A write is admitted only once both AW and
  *    the last W beat have arrived (`newWReq` from [[SplitTransactionModel]]).
  * 2. Outstanding caps still come from that base class. AXI ready does not
  *    look at the issuer, so a request can sit in the pipe until the issuer
  *    reaches it. Ready goes low when the programmed outstanding cap is full.
  * 3. Admitted ops share one issuer. If a read and a write are admitted in the
  *    same cycle, the read is ordered first.
  * 4. `start = max(tCycle, nextService)`. The other op, if any, starts at
  *    `start + occupancy` of the first. `nextService` becomes the end of the
  *    last op admitted this cycle.
  * 5. Occupancy is `max(programmedServiceCycles, axiLen + 1)`. The programmed
  *    value is a minimum device service time. The beat count is the minimum
  *    time to move the burst across a one-beat-per-cycle port. They are not
  *    added.
  * 6. The timing-model response is presented when
  *    `tCycle >= start + latency - egressUnitDelay`, same formula as
  *    [[LatencyPipe]]. One response of each type can leave per cycle.
  * 7. Logical write bytes and device write bytes both increase by the AXI
  *    transfer size. Write amplification is 1. An endurance budget of 0
  *    disables the check. A nonzero budget sets a sticky flag when the next
  *    write would pass it and does not drop, corrupt, or delay the write.
  * 8. Retention does not change data or timing. With `retentionSets > 0` and
  *    `retentionCycles > 0`, a direct-mapped table of line timestamps classifies
  *    an admitted read as fresh, stale (`age > retentionCycles`), or unknown
  *    (miss or conflict). A miss is not an error. `retentionCycles == 0`
  *    leaves the counters at zero.
  */
case class TechSpecMemoryConfig(
  params:                     BaseParams,
  retentionSets:              Int     = 0,
  retentionGranularityBytes:  Int     = 64,
  requestTrace:               Boolean = false,
) extends BaseConfig {
  require(
    retentionSets == 0 || (retentionSets >= 2 && Integer.bitCount(retentionSets) == 1),
    s"retentionSets must be 0 or a power of two >= 2, got $retentionSets",
  )
  require(
    retentionGranularityBytes >= 1 && Integer.bitCount(retentionGranularityBytes) == 1,
    s"retentionGranularityBytes must be a positive power of two, got $retentionGranularityBytes",
  )

  def elaborate()(implicit p: Parameters): TechSpecMemoryModel = Module(new TechSpecMemoryModel(this))
}

class TechSpecMMRegIO(val cfg: TechSpecMemoryConfig)(implicit p: Parameters) extends SplitTransactionMMRegIO(cfg) {
  val readLatency          = Input(UInt(32.W))
  val writeLatency         = Input(UInt(32.W))
  val readServiceCycles    = Input(UInt(32.W))
  val writeServiceCycles   = Input(UInt(32.W))
  // FASED's control register file is 32 bits wide (CtrlNastiKey). Wider
  // fields fail when the bridge attaches them. Counters wrap at 2^32.
  val enduranceLimitBytes  = Input(UInt(32.W))
  val retentionCycles      = Input(UInt(32.W))
  // Ignored unless the model was elaborated with requestTrace. Kept
  // unconditional so every TechSpec runtime config has the same register.
  val traceEnable          = Input(UInt(1.W))

  val deviceReadBytes       = Output(UInt(32.W))
  val deviceWriteBytes      = Output(UInt(32.W))
  val logicalWriteBytes     = Output(UInt(32.W))
  val enduranceExceeded     = Output(Bool())
  val admittedReads         = Output(UInt(32.W))
  val admittedWrites        = Output(UInt(32.W))
  val issuerBusyCycles      = Output(UInt(32.W))
  val retentionFreshReads   = Output(UInt(32.W))
  val retentionStaleReads   = Output(UInt(32.W))
  val retentionUnknownReads = Output(UInt(32.W))

  val registers = maxReqRegisters ++ Seq(
    (readLatency         -> RuntimeSetting(30, "Read latency in target cycles, including the egress cycle", min = 1)),
    (writeLatency        -> RuntimeSetting(30, "Write latency in target cycles, including the egress cycle", min = 1)),
    (readServiceCycles   -> RuntimeSetting(1, "Minimum read issuer occupancy in target cycles", min = 1)),
    (writeServiceCycles  -> RuntimeSetting(1, "Minimum write issuer occupancy in target cycles", min = 1)),
    (enduranceLimitBytes -> RuntimeSetting(0, "Device-write-byte budget; 0 disables the flag")),
    (retentionCycles     -> RuntimeSetting(0, "Retention window in target cycles; 0 disables classification")),
    (traceEnable         -> RuntimeSetting(0, "Print TECHSPEC lines; no effect unless elaborated with requestTrace", max = Some(BigInt(1)))),
  )

  def requestSettings(): Unit = {
    Console.println(s"${UNDERLINED}Generating a runtime configuration for a technology-spec memory${RESET}")
  }
}

class TechSpecMemoryIO(val cfg: TechSpecMemoryConfig)(implicit p: Parameters) extends SplitTransactionModelIO()(p) {
  val mmReg = new TechSpecMMRegIO(cfg)
}

class TechSpecMemoryModel(cfg: TechSpecMemoryConfig)(implicit p: Parameters) extends SplitTransactionModel(cfg)(p) {
  lazy val io = IO(new TechSpecMemoryIO(cfg))

  val longName = "Technology-spec byte-addressable memory"
  def printTimingModelGenerationConfig: Unit = {
    println(s"  Retention sets: ${cfg.retentionSets}")
    println(s"  Retention granularity bytes: ${cfg.retentionGranularityBytes}")
    println(s"  Request trace: ${cfg.requestTrace}")
  }

  val readLatency        = io.mmReg.readLatency
  val writeLatency       = io.mmReg.writeLatency
  val nextService        = RegInit(0.U(64.W))

  val readAdmit  = nastiReq.ar.fire
  val writeAdmit = newWReq

  val readBeats  = (nastiReq.ar.bits.len +& 1.U).pad(32)
  val writeBeats = (awQueue.io.deq.bits.len +& 1.U).pad(32)
  val readOcc    = Mux(io.mmReg.readServiceCycles > readBeats, io.mmReg.readServiceCycles, readBeats)
  val writeOcc   = Mux(io.mmReg.writeServiceCycles > writeBeats, io.mmReg.writeServiceCycles, writeBeats)

  val baseStart  = Mux(tCycle > nextService, tCycle, nextService)
  val readStart  = baseStart
  val writeStart = Mux(readAdmit, readStart + readOcc, baseStart)
  val readRelease  = readStart + readLatency - egressUnitDelay.U
  val writeRelease = writeStart + writeLatency - egressUnitDelay.U

  when(readAdmit || writeAdmit) {
    nextService := Mux(writeAdmit, writeStart + writeOcc, readStart + readOcc)
  }

  val readPipe = Module(new Queue(new ReadPipeEntry(p(NastiKey)), cfg.maxReads, flow = true))
  readPipe.io.enq.valid             := readAdmit
  readPipe.io.enq.bits.xaction      := ReadResponseMetaData(p(NastiKey), nastiReq.ar.bits)
  readPipe.io.enq.bits.releaseCycle := readRelease
  val readDone = readPipe.io.deq.bits.releaseCycle <= tCycle
  rResp.valid           := readPipe.io.deq.valid && readDone
  rResp.bits            := readPipe.io.deq.bits.xaction
  readPipe.io.deq.ready := rResp.ready && readDone
  assert(readPipe.io.enq.ready || !readAdmit, "TechSpec read pipe would overflow.")

  val writePipe = Module(new Queue(new WritePipeEntry(p(NastiKey)), cfg.maxWrites, flow = true))
  writePipe.io.enq.valid             := writeAdmit
  writePipe.io.enq.bits.xaction      := WriteResponseMetaData(p(NastiKey), awQueue.io.deq.bits)
  writePipe.io.enq.bits.releaseCycle := writeRelease
  val writeDone = writePipe.io.deq.bits.releaseCycle <= tCycle
  wResp.valid            := writePipe.io.deq.valid && writeDone
  wResp.bits             := writePipe.io.deq.bits.xaction
  writePipe.io.deq.ready := wResp.ready && writeDone
  assert(writePipe.io.enq.ready || !writeAdmit, "TechSpec write pipe would overflow.")

  val deviceReadBytes   = RegInit(0.U(32.W))
  val deviceWriteBytes  = RegInit(0.U(32.W))
  val logicalWriteBytes = RegInit(0.U(32.W))
  val enduranceExceeded = RegInit(false.B)
  val admittedReads     = RegInit(0.U(32.W))
  val admittedWrites    = RegInit(0.U(32.W))
  val issuerBusyCycles  = RegInit(0.U(32.W))

  def xferBytes(len: UInt, size: UInt): UInt = (len +& 1.U) << size

  when(readAdmit) {
    deviceReadBytes := deviceReadBytes + xferBytes(nastiReq.ar.bits.len, nastiReq.ar.bits.size)
    admittedReads   := admittedReads + 1.U
  }
  when(writeAdmit) {
    val nbytes = xferBytes(awQueue.io.deq.bits.len, awQueue.io.deq.bits.size)
    val next   = deviceWriteBytes +& nbytes
    // Account only. Crossing the budget must not change ready or release time.
    when(io.mmReg.enduranceLimitBytes =/= 0.U && next > io.mmReg.enduranceLimitBytes) {
      enduranceExceeded := true.B
    }
    deviceWriteBytes  := deviceWriteBytes + nbytes
    logicalWriteBytes := logicalWriteBytes + nbytes
    admittedWrites    := admittedWrites + 1.U
  }

  when((tCycle < nextService) || readAdmit || writeAdmit) {
    issuerBusyCycles := issuerBusyCycles + 1.U
  }

  io.mmReg.deviceReadBytes   := deviceReadBytes
  io.mmReg.deviceWriteBytes  := deviceWriteBytes
  io.mmReg.logicalWriteBytes := logicalWriteBytes
  io.mmReg.enduranceExceeded := enduranceExceeded
  io.mmReg.admittedReads     := admittedReads
  io.mmReg.admittedWrites    := admittedWrites
  io.mmReg.issuerBusyCycles  := issuerBusyCycles

  val freshReads   = RegInit(0.U(32.W))
  val staleReads   = RegInit(0.U(32.W))
  val unknownReads = RegInit(0.U(32.W))
  if (cfg.retentionSets > 0) {
    val granBits = log2Ceil(cfg.retentionGranularityBytes)
    val setBits  = log2Ceil(cfg.retentionSets)
    val addrBits = p(NastiKey).addrBits
    require(addrBits > granBits + setBits, s"address width $addrBits cannot hold a retention tag")
    val tagBits  = addrBits - granBits - setBits
    val retValid = RegInit(VecInit(Seq.fill(cfg.retentionSets)(false.B)))
    val retTag   = Reg(Vec(cfg.retentionSets, UInt(tagBits.W)))
    val retWrite = Reg(Vec(cfg.retentionSets, UInt(32.W)))

    def setIndex(addr: UInt): UInt = addr(granBits + setBits - 1, granBits)
    def lineTag(addr: UInt): UInt  = addr(addrBits - 1, granBits + setBits)

    val rIdx = setIndex(nastiReq.ar.bits.addr)
    val rTag = lineTag(nastiReq.ar.bits.addr)
    val rHit = retValid(rIdx) && retTag(rIdx) === rTag
    when(readAdmit && io.mmReg.retentionCycles =/= 0.U) {
      when(!rHit) {
        unknownReads := unknownReads + 1.U
      }.elsewhen((tCycle(31, 0) - retWrite(rIdx)) > io.mmReg.retentionCycles) {
        staleReads := staleReads + 1.U
      }.otherwise {
        freshReads := freshReads + 1.U
      }
    }
    when(writeAdmit) {
      val wIdx = setIndex(awQueue.io.deq.bits.addr)
      retValid(wIdx) := true.B
      retTag(wIdx)   := lineTag(awQueue.io.deq.bits.addr)
      retWrite(wIdx) := tCycle(31, 0)
    }
  }
  io.mmReg.retentionFreshReads   := freshReads
  io.mmReg.retentionStaleReads   := staleReads
  io.mmReg.retentionUnknownReads := unknownReads

  if (cfg.requestTrace) {
    val enabled = io.mmReg.traceEnable === 1.U
    when(enabled && readAdmit) {
      printf(
        "TECHSPEC,%d,%d,%x,%d,%d,%d,%d,%d\n",
        tCycle,
        0.U,
        nastiReq.ar.bits.addr,
        nastiReq.ar.bits.id,
        nastiReq.ar.bits.len,
        nastiReq.ar.bits.size,
        readStart,
        readRelease,
      )
    }
    when(enabled && writeAdmit) {
      printf(
        "TECHSPEC,%d,%d,%x,%d,%d,%d,%d,%d\n",
        tCycle,
        1.U,
        awQueue.io.deq.bits.addr,
        awQueue.io.deq.bits.id,
        awQueue.io.deq.bits.len,
        awQueue.io.deq.bits.size,
        writeStart,
        writeRelease,
      )
    }
  }
}
