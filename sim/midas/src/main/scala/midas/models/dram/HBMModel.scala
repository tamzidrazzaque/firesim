package midas
package models

import chisel3._
import chisel3.util._

import org.chipsalliance.cde.config.Parameters

import junctions.NastiKey
import midas.widgets._

import firesim.lib.nasti._

/** =============================================================================
  * HBM2 (JESD235) memory timing model for FASED
  * =============================================================================
  *
  * Models a single HBM2 channel operating in pseudo-channel (PC) mode with a
  * first-ready FCFS memory access scheduler. Structurally this borrows from
  * FirstReadyFCFSModel, with the DDR3 rank/bank hierarchy replaced by the
  * JESD235 hierarchy:
  *
  *   - Pseudo-channels take the structural place of ranks. Each PC has
  *     independent bank state and an independent data bus, so there is no
  *     rank-to-rank data-bus switching penalty (tRTRS) between PCs.
  *
  *   - The channel has *two* command buses, mirroring JESD235's split
  *     row (R[6:0]) and column (C[8:0]) buses: one row command (ACT / PRE /
  *     REF / REFSB) and one column command (RD / WR) may issue in the same
  *     cycle. An ACT occupies the row bus for two cycles (JESD235 ACTs are
  *     two-frame commands).
  *
  *   - Bank groups add the JESD235 short/long timing split. Same-bank-group
  *     accesses are constrained by the *long* parameters (tCCDL, tRRDL,
  *     tWTRL), different-bank-group accesses by the *short* ones (tCCDS,
  *     tRRDS, tWTRS).
  *
  *   - Row-to-column delay is asymmetric: tRCDRD for reads, tRCDWR for
  *     writes.
  *
  *   - The read-to-write turnaround is enforced at pseudo-channel scope as
  *     nCL + nBL + 2 - nCWL, per JESD235.
  *
  *   - Refresh is runtime-selectable between all-bank refresh (REFab,
  *     default) and per-bank refresh (REFSB). In REFSB mode one bank is
  *     refreshed per tREFI/16 interval in round-robin order; only the
  *     refreshed bank is blocked (for tRFCSB) while the other banks keep
  *     serving traffic. REFSB commands count toward the tFAW window and are
  *     spaced by tRREFD, per JESD235.
  *
  * All timing parameters are runtime-programmable registers (in units of the
  * memory controller clock, like all FASED timings), so alternate timing
  * tables -- e.g. the PARE table -- can be loaded from a runtime config
  * without regenerating the FPGA image.
  */

/** Organization of a single HBM2 channel in pseudo-channel mode.
  *
  * @param maxPseudoChannels
  *   pseudo channels per channel (2 in HBM2 PC mode)
  * @param maxBankGroups
  *   bank groups per pseudo channel (4 in HBM2)
  * @param banksPerGroup
  *   banks per bank group (4 in HBM2)
  * @param channelSize
  *   bytes of addressable storage modeled by this instance. Like
  *   DramOrganizationParams.dramSize this is an upper bound used to size
  *   address registers; the actual decode is runtime-programmable.
  */
case class HBMOrganizationParams(
  maxPseudoChannels: Int,
  maxBankGroups:     Int,
  banksPerGroup:     Int,
  channelSize:       BigInt,
  lineBits:          Int = 8,
) {
  require(isPow2(maxPseudoChannels) && maxPseudoChannels >= 2)
  require(isPow2(maxBankGroups))
  require(isPow2(banksPerGroup))
  require(isPow2(channelSize))
  def maxBanks   = maxBankGroups * banksPerGroup // banks per pseudo channel
  def bankBits   = log2Up(maxBanks)
  def bankGroupBits = log2Up(maxBankGroups)
  def pcBits     = log2Up(maxPseudoChannels)
  def rowBits    = log2Ceil(channelSize) - lineBits
  def maxRows    = 1 << rowBits
}

/** Named HBM2 timing tables, in units of the controller clock (CK).
  *
  * The HBM2 speed grades follow JESD235B/D; secondary parameters (tRRD, tFAW,
  * tRFC, tRFCSB, tRREFD, tREFI) are resolved from their ns specs at the
  * corresponding tCK (1250 ps / 1000 ps / 833 ps).
  *
  * PARE is a placeholder that currently aliases HBM2-2400: the real PARE
  * timing table should be dropped in here once it is provided.
  */
object HBMTimingTables {
  val hbm2_2400: Map[String, BigInt] = Map(
    "tCAS"   -> 17, // nCL
    "tCWD"   -> 6,  // nCWL
    "tBL"    -> 2,  // nBL (BL4 over DDR)
    "tCMD"   -> 1,
    "tCCDS"  -> 2,
    "tCCDL"  -> 4,
    "tRRDS"  -> 5,  // 4 ns @ 833 ps
    "tRRDL"  -> 5,
    "tFAW"   -> 19, // 15 ns
    "tWTRS"  -> 8,
    "tWTRL"  -> 10,
    "tRCDRD" -> 17,
    "tRCDWR" -> 14,
    "tRP"    -> 17,
    "tRAS"   -> 40,
    "tRC"    -> 57,
    "tRTP"   -> 6,  // nRTPL
    "tWR"    -> 19,
    "tREFI"  -> 4682, // 3.9 us
    "tRFC"   -> 421,  // 350 ns (8Gb per-PC density)
    "tRFCSB" -> 193,  // 160 ns (8Gb, per-bank refresh); ceil(160000/833)
    "tRREFD" -> 10,   // 8 ns
  ).map { case (k, v) => k -> BigInt(v) }

  val hbm2_2000: Map[String, BigInt] = Map(
    "tCAS"   -> 14,
    "tCWD"   -> 5,
    "tBL"    -> 2,
    "tCMD"   -> 1,
    "tCCDS"  -> 2,
    "tCCDL"  -> 4,
    "tRRDS"  -> 4,
    "tRRDL"  -> 4,
    "tFAW"   -> 15,
    "tWTRS"  -> 6,
    "tWTRL"  -> 8,
    "tRCDRD" -> 14,
    "tRCDWR" -> 12,
    "tRP"    -> 14,
    "tRAS"   -> 34,
    "tRC"    -> 48,
    "tRTP"   -> 5,
    "tWR"    -> 16,
    "tREFI"  -> 3900,
    "tRFC"   -> 350,
    "tRFCSB" -> 160,
    "tRREFD" -> 8,
  ).map { case (k, v) => k -> BigInt(v) }

  val hbm2_1600: Map[String, BigInt] = Map(
    "tCAS"   -> 10,
    "tCWD"   -> 4,
    "tBL"    -> 2,
    "tCMD"   -> 1,
    "tCCDS"  -> 2,
    "tCCDL"  -> 4,
    "tRRDS"  -> 4,
    "tRRDL"  -> 4,
    "tFAW"   -> 12,
    "tWTRS"  -> 5,
    "tWTRL"  -> 6,
    "tRCDRD" -> 10,
    "tRCDWR" -> 8,
    "tRP"    -> 10,
    "tRAS"   -> 24,
    "tRC"    -> 34,
    "tRTP"   -> 4,
    "tWR"    -> 12,
    "tREFI"  -> 3120,
    "tRFC"   -> 280,
    "tRFCSB" -> 128,
    "tRREFD" -> 7,
  ).map { case (k, v) => k -> BigInt(v) }

  // TODO(PARE): replace with the real PARE timing table when it is provided.
  val pare: Map[String, BigInt] = hbm2_2400

  // _1 = table, _2 = long name shown in interactive selection
  val grades = Seq(
    (hbm2_2400 -> "HBM2-2400 (JESD235, tCK = 833 ps)"),
    (hbm2_2000 -> "HBM2-2000 (JESD235, tCK = 1000 ps)"),
    (hbm2_1600 -> "HBM2-1600 (JESD235, tCK = 1250 ps)"),
    (pare      -> "PARE (PLACEHOLDER -- currently aliases HBM2-2400)"),
  )
}

/** Runtime-programmable HBM2 timing registers, in controller-clock units.
  * Defaults correspond to HBM2-2400 (the project reference table).
  */
class HBMProgrammableTimings
    extends Bundle
    with HasDRAMMASConstants
    with HasProgrammableRegisters
    with HasConsoleUtils {
  val tCAS   = UInt(maxDRAMTimingBits.W)
  val tCWD   = UInt(maxDRAMTimingBits.W)
  val tBL    = UInt(maxDRAMTimingBits.W)
  val tCMD   = UInt(maxDRAMTimingBits.W)
  val tCCDS  = UInt(maxDRAMTimingBits.W)
  val tCCDL  = UInt(maxDRAMTimingBits.W)
  val tRRDS  = UInt(maxDRAMTimingBits.W)
  val tRRDL  = UInt(maxDRAMTimingBits.W)
  val tFAW   = UInt(maxDRAMTimingBits.W)
  val tWTRS  = UInt(maxDRAMTimingBits.W)
  val tWTRL  = UInt(maxDRAMTimingBits.W)
  val tRCDRD = UInt(maxDRAMTimingBits.W)
  val tRCDWR = UInt(maxDRAMTimingBits.W)
  val tRP    = UInt(maxDRAMTimingBits.W)
  val tRAS   = UInt(maxDRAMTimingBits.W)
  val tRC    = UInt(maxDRAMTimingBits.W)
  val tRTP   = UInt(maxDRAMTimingBits.W)
  val tWR    = UInt(maxDRAMTimingBits.W)
  val tREFI  = UInt(tREFIBits.W)
  val tRFC   = UInt(tRFCBits.W)
  val tRFCSB = UInt(tRFCBits.W)
  val tRREFD = UInt(maxDRAMTimingBits.W)

  val registers = Seq(
    tCAS   -> RuntimeSetting(17, "CAS (read) latency, nCL"),
    tCWD   -> RuntimeSetting(6, "Write latency, nCWL"),
    tBL    -> RuntimeSetting(2, "Burst duration in CK, nBL"),
    tCMD   -> RuntimeSetting(1, "Command transport time"),
    tCCDS  -> RuntimeSetting(2, "CAS-to-CAS delay, different bank group (tCCDS)"),
    tCCDL  -> RuntimeSetting(4, "CAS-to-CAS delay, same bank group (tCCDL)"),
    tRRDS  -> RuntimeSetting(5, "ACT-to-ACT delay, different bank group (tRRDS)"),
    tRRDL  -> RuntimeSetting(5, "ACT-to-ACT delay, same bank group (tRRDL)"),
    tFAW   -> RuntimeSetting(19, "Four-activate window (tFAW)"),
    tWTRS  -> RuntimeSetting(8, "Write-to-read turnaround, different bank group (tWTRS)"),
    tWTRL  -> RuntimeSetting(10, "Write-to-read turnaround, same bank group (tWTRL)"),
    tRCDRD -> RuntimeSetting(17, "ACT-to-read delay (tRCDRD)"),
    tRCDWR -> RuntimeSetting(14, "ACT-to-write delay (tRCDWR)"),
    tRP    -> RuntimeSetting(17, "Row precharge delay (tRP)"),
    tRAS   -> RuntimeSetting(40, "Row access strobe delay (tRAS)"),
    tRC    -> RuntimeSetting(57, "Row cycle time (tRC)"),
    tRTP   -> RuntimeSetting(6, "Read-to-precharge delay (tRTPL)"),
    tWR    -> RuntimeSetting(19, "Write recovery time (tWR)"),
    tREFI  -> RuntimeSetting(4682, "Refresh interval (tREFI); 0 disables refresh"),
    tRFC   -> RuntimeSetting(421, "Refresh cycle time, all-bank (tRFCab)"),
    tRFCSB -> RuntimeSetting(193, "Refresh cycle time, single-bank (tRFCSB)"),
    tRREFD -> RuntimeSetting(10, "REFSB-to-REFSB / ACT-to-REFSB delay (tRREFD)"),
  )

  def setTimingTable(table: Map[String, BigInt]): Unit = {
    registers.foreach { case (elem, reg) => reg.set(table(getName(elem))) }
  }
}

abstract class HBMBaseConfig extends BaseConfig with HasDRAMMASConstants {
  def hbmKey:     HBMOrganizationParams
  def backendKey: DRAMBackendKey
}

case class HBMModelConfig(
  hbmKey:                HBMOrganizationParams,
  schedulerWindowSize:   Int,
  transactionQueueDepth: Int,
  backendKey:            DRAMBackendKey = DRAMBackendKey(4, 4, DRAMMasEnums.backendLatencyBits),
  params:                BaseParams,
) extends HBMBaseConfig {
  def elaborate()(implicit p: Parameters): HBMModel = Module(new HBMModel(this))
}

class HBMMMRegIO(val cfg: HBMModelConfig) extends MMRegIO(cfg) with HasConsoleUtils {
  // Default address layout, LSB to MSB:
  //   [ line offset (6b) | lines-per-row (4b) | bank (4b, group in low bits)
  //     | pseudo channel (1b) | row ]
  // This gives a 1 KiB page per (PC, bank) and interleaves sequential rows
  // across bank groups.
  val bankAddr = Input(
    new ProgrammableSubAddr(
      maskBits      = cfg.hbmKey.bankBits,
      longName      = "Bank Address",
      defaultOffset = 10,
      defaultMask   = cfg.hbmKey.maxBanks - 1,
    )
  )

  val pcAddr = Input(
    new ProgrammableSubAddr(
      maskBits      = cfg.hbmKey.pcBits,
      longName      = "Pseudo Channel Address",
      defaultOffset = 10 + cfg.hbmKey.bankBits,
      defaultMask   = cfg.hbmKey.maxPseudoChannels - 1,
    )
  )

  val defaultRowOffset = 10 + cfg.hbmKey.bankBits + cfg.hbmKey.pcBits
  val rowAddr = Input(
    new ProgrammableSubAddr(
      maskBits      = cfg.hbmKey.rowBits,
      longName      = "Row Address",
      defaultOffset = defaultRowOffset,
      defaultMask   = (cfg.hbmKey.channelSize >> defaultRowOffset) - 1,
    )
  )

  // Page policy 1 = open, 0 = closed
  val openPagePolicy = Input(Bool())
  // Refresh mode 1 = per-bank (REFSB), 0 = all-bank (REFab)
  val perBankRefresh = Input(Bool())
  // Additional latency added to read data beats after they leave the devices
  val backendLatency = Input(UInt(cfg.backendKey.latencyBits.W))

  val hbmTimings = Input(new HBMProgrammableTimings())

  val schedulerWindowSize   = Input(UInt(log2Ceil(cfg.schedulerWindowSize).W))
  val transactionQueueDepth = Input(UInt(log2Ceil(cfg.transactionQueueDepth).W))

  val registers = Seq(
    openPagePolicy        -> RuntimeSetting(1, "Open-Page Policy"),
    perBankRefresh        -> RuntimeSetting(0, "Per-bank refresh (1 = REFSB, 0 = all-bank REFab)"),
    backendLatency        -> RuntimeSetting(
      2,
      "Backend Latency",
      min = 1,
      max = Some(1 << (cfg.backendKey.latencyBits - 1)),
    ),
    schedulerWindowSize   -> RuntimeSetting(
      default = cfg.schedulerWindowSize,
      query   = "Reference queue depth",
      min     = 1,
      max     = Some(cfg.schedulerWindowSize),
    ),
    transactionQueueDepth -> RuntimeSetting(
      default = cfg.transactionQueueDepth,
      query   = "Transaction queue depth",
      min     = 1,
      max     = Some(cfg.transactionQueueDepth),
    ),
  )

  def requestSettings(): Unit = {
    Console.println("Configuring an HBM2 (JESD235) First-Ready FCFS model")
    val gradeIdx = requestSeqSelection(
      "Select an HBM timing table:",
      HBMTimingTables.grades.map(_._2),
    )
    hbmTimings.setTimingTable(HBMTimingTables.grades(gradeIdx)._1)
  }
}

// Scheduler entry: a decoded memory reference with HBM coordinates
class HBMEntry(nastiParams: NastiParameters, cfg: HBMBaseConfig)(implicit p: Parameters) extends Bundle {
  val xaction   = new TransactionMetaData(nastiParams)
  val rowAddr   = UInt(cfg.hbmKey.rowBits.W)
  // Bank address within a pseudo channel; the bank group lives in the low
  // bankGroupBits so that sequential row buffers interleave across groups.
  val bankAddr   = UInt(cfg.hbmKey.bankBits.W)
  val bankAddrOH = UInt(cfg.hbmKey.maxBanks.W)
  val pcAddr     = UInt(cfg.hbmKey.pcBits.W)
  val pcAddrOH   = UInt(cfg.hbmKey.maxPseudoChannels.W)

  val isReady = Bool() // Set when this entry hits in an open row buffer
  val mayPRE  = Bool() // Set when no other entries hit the same open row

  def bankGroupAddr:   UInt = bankAddr(cfg.hbmKey.bankGroupBits - 1, 0)
  def bankGroupAddrOH: UInt = UIntToOH(bankGroupAddr)

  def decode(from: XactionSchedulerEntry, mmReg: HBMMMRegIO): Unit = {
    xaction    := from.xaction
    bankAddr   := mmReg.bankAddr.getSubAddr(from.addr)
    bankAddrOH := UIntToOH(bankAddr)
    rowAddr    := mmReg.rowAddr.getSubAddr(from.addr)
    pcAddr     := mmReg.pcAddr.getSubAddr(from.addr)
    pcAddrOH   := UIntToOH(pcAddr)
  }

  def addrMatch(pc: UInt, bank: UInt, row: Option[UInt] = None): Bool = {
    val rowHit = row.foldLeft(true.B)({ case (p, addr) => p && addr === rowAddr })
    pc === pcAddr && bank === bankAddr && rowHit
  }

  def wantPRE(): Bool = !isReady && mayPRE
  def wantACT(): Bool = !isReady
}

// ============================================================================
// Bank state tracker
// ============================================================================
// Differences from the DDR3 BankStateTracker:
//   - split read/write column-access legality (tRCDRD vs tRCDWR)
//   - write recovery uses the explicit burst duration tBL
//   - REFSB support: a per-bank refresh occupies (only) this bank for tRFCSB

class HBMBankStateTrackerO(val key: HBMOrganizationParams) extends Bundle {
  import DRAMMasEnums._
  val canCASR = Output(Bool())
  val canCASW = Output(Bool())
  val canPRE  = Output(Bool())
  val canACT  = Output(Bool())
  val openRow = Output(UInt(key.rowBits.W))
  val state   = Output(Bool())

  def isRowHit(ref: HBMEntry): Bool = ref.rowAddr === openRow && state === bank_active
}

class HBMBankStateTrackerIO(val key: HBMOrganizationParams) extends Bundle {
  import DRAMMasEnums._
  val timings         = Input(new HBMProgrammableTimings)
  val selectedCmd     = Input(cmd_nop.cloneType)
  val autoPRE         = Input(Bool())
  val cmdRow          = Input(UInt(key.rowBits.W))
  val out             = new HBMBankStateTrackerO(key)
  val cmdUsesThisBank = Input(Bool())
}

class HBMBankStateTracker(key: HBMOrganizationParams) extends Module with HasDRAMMASConstants {
  import DRAMMasEnums._
  val io = IO(new HBMBankStateTrackerIO(key))

  val state       = RegInit(bank_idle)
  val openRowAddr = Reg(UInt(key.rowBits.W))

  val nextLegalPRE  = Module(new DownCounter(maxDRAMTimingBits))
  val nextLegalACT  = Module(new DownCounter(tRFCBits))
  val nextLegalCASR = Module(new DownCounter(maxDRAMTimingBits))
  val nextLegalCASW = Module(new DownCounter(maxDRAMTimingBits))

  Seq(nextLegalPRE, nextLegalACT, nextLegalCASR, nextLegalCASW).foreach { mod =>
    mod.io.decr      := true.B
    mod.io.set.valid := false.B
    mod.io.set.bits  := DontCare
  }

  when(io.cmdUsesThisBank) {
    switch(io.selectedCmd) {
      is(cmd_act) {
        assert(io.out.canACT, "HBM Bank Timing Violation: Controller issued ACT command illegally")
        state                      := bank_active
        openRowAddr                := io.cmdRow
        nextLegalCASR.io.set.valid := true.B
        nextLegalCASR.io.set.bits  := io.timings.tRCDRD - 1.U
        nextLegalCASW.io.set.valid := true.B
        nextLegalCASW.io.set.bits  := io.timings.tRCDWR - 1.U
        nextLegalPRE.io.set.valid  := true.B
        nextLegalPRE.io.set.bits   := io.timings.tRAS - 1.U
        nextLegalACT.io.set.valid  := true.B
        nextLegalACT.io.set.bits   := io.timings.tRC - 1.U
      }
      is(cmd_casr) {
        assert(io.out.canCASR, "HBM Bank Timing Violation: Controller issued CASR command illegally")
        when(io.autoPRE) {
          state                     := bank_idle
          nextLegalACT.io.set.valid := true.B
          nextLegalACT.io.set.bits  := io.timings.tRTP + io.timings.tRP - 1.U
        }.otherwise {
          nextLegalPRE.io.set.valid := true.B
          nextLegalPRE.io.set.bits  := io.timings.tRTP - 1.U
        }
      }
      is(cmd_casw) {
        assert(io.out.canCASW, "HBM Bank Timing Violation: Controller issued CASW command illegally")
        when(io.autoPRE) {
          state                     := bank_idle
          nextLegalACT.io.set.valid := true.B
          nextLegalACT.io.set.bits  := io.timings.tCWD + io.timings.tBL + io.timings.tWR +
            io.timings.tRP - 1.U
        }.otherwise {
          nextLegalPRE.io.set.valid := true.B
          nextLegalPRE.io.set.bits  := io.timings.tCWD + io.timings.tBL + io.timings.tWR - 1.U
        }
      }
      is(cmd_pre) {
        assert(io.out.canPRE, "HBM Bank Timing Violation: Controller issued PRE command illegally")
        state                     := bank_idle
        nextLegalACT.io.set.valid := true.B
        nextLegalACT.io.set.bits  := io.timings.tRP - 1.U
      }
      is(cmd_refsb) {
        assert(io.out.canACT, "HBM Bank Timing Violation: Controller issued REFSB to a non-idle bank")
        // Bank stays idle; it is simply unavailable for tRFCSB
        nextLegalACT.io.set.valid := true.B
        nextLegalACT.io.set.bits  := io.timings.tRFCSB - 1.U
      }
    }
  }

  io.out.canCASR := (state === bank_active) && nextLegalCASR.io.idle // Controller must check rowAddr
  io.out.canCASW := (state === bank_active) && nextLegalCASW.io.idle // Controller must check rowAddr
  io.out.canPRE  := (state === bank_active) && nextLegalPRE.io.idle
  io.out.canACT  := (state === bank_idle) && nextLegalACT.io.idle
  io.out.state   := state
  io.out.openRow := openRowAddr
}

// ============================================================================
// Pseudo-channel state tracker
// ============================================================================
// Owns:
//   - per-bank state (HBMBankStateTracker instances)
//   - per-bank-group CAS/ACT legality (long timings: tCCDL, tRRDL, tWTRL)
//   - pseudo-channel-scope CAS/ACT legality (short timings: tCCDS, tRRDS,
//     tWTRS; read-write turnarounds; tFAW)
//   - refresh state: all-bank (tREFI/tRFCab) or per-bank (tREFI/16, tRFCSB,
//     tRREFD, round-robin bank pointer)
//
// The tracker sees both command buses: one row command (ACT/PRE/REF/REFSB)
// and one column command (CASR/CASW) may target this PC in the same cycle,
// as long as they target different banks (the model's scheduler guarantees
// this). There are no cross-PC timing constraints: pseudo channels have
// separate data buses and (in this model) separate row/column bus slots.

class HBMPseudoChannelStateTrackerO(val key: HBMOrganizationParams) extends Bundle {
  import DRAMMasEnums._
  val canCASR   = Output(Bool())
  val canCASW   = Output(Bool())
  val canACT    = Output(Bool())
  val canPRE    = Output(Bool())
  val canREF    = Output(Bool())
  val canREFSB  = Output(Bool())
  val wantREF   = Output(Bool())
  val refsbBank = Output(UInt(key.bankBits.W))
  val state     = Output(rank_active.cloneType)
  val bgCanCASR = Vec(key.maxBankGroups, Output(Bool()))
  val bgCanCASW = Vec(key.maxBankGroups, Output(Bool()))
  val bgCanACT  = Vec(key.maxBankGroups, Output(Bool()))
  val banks     = Vec(key.maxBanks, Output(new HBMBankStateTrackerO(key)))
}

class HBMPseudoChannelStateTrackerIO(val key: HBMOrganizationParams)
    extends Bundle
    with HasDRAMMASConstants {
  import DRAMMasEnums._
  val timings          = Input(new HBMProgrammableTimings)
  val perBankRefresh   = Input(Bool())
  // Split command buses: row commands (ACT/PRE/REF/REFSB) and column
  // commands (CASR/CASW) may arrive in the same cycle.
  val rowCmd           = Input(cmd_nop.cloneType)
  val colCmd           = Input(cmd_nop.cloneType)
  val rowCmdUsesThisPC = Input(Bool())
  val colCmdUsesThisPC = Input(Bool())
  val rowBankOH        = Input(UInt(key.maxBanks.W))
  val colBankOH        = Input(UInt(key.maxBanks.W))
  val rowBankGroupOH   = Input(UInt(key.maxBankGroups.W))
  val colBankGroupOH   = Input(UInt(key.maxBankGroups.W))
  val cmdRow           = Input(UInt(key.rowBits.W))
  val autoPRE          = Input(Bool())
  val pc               = new HBMPseudoChannelStateTrackerO(key)
  val tCycle           = Input(UInt(maxDRAMTimingBits.W))
}

class HBMPseudoChannelStateTracker(key: HBMOrganizationParams) extends Module with HasDRAMMASConstants {
  import DRAMMasEnums._

  val io = IO(new HBMPseudoChannelStateTrackerIO(key))
  val t  = io.timings

  // Pseudo-channel-scope legality (short / cross-bank-group constraints)
  val nextLegalPRE   = Module(new DownCounter(maxDRAMTimingBits))
  val nextLegalACT   = Module(new DownCounter(tRFCBits))
  val nextLegalCASR  = Module(new DownCounter(maxDRAMTimingBits))
  val nextLegalCASW  = Module(new DownCounter(maxDRAMTimingBits))
  val nextLegalREFSB = Module(new DownCounter(tRFCBits))

  // Bank-group-scope legality (long / same-bank-group constraints)
  val bgNextLegalCASR = Seq.fill(key.maxBankGroups)(Module(new DownCounter(maxDRAMTimingBits)))
  val bgNextLegalCASW = Seq.fill(key.maxBankGroups)(Module(new DownCounter(maxDRAMTimingBits)))
  val bgNextLegalACT  = Seq.fill(key.maxBankGroups)(Module(new DownCounter(maxDRAMTimingBits)))

  val refCounter = RegInit(0.U(tREFIBits.W))
  val state      = RegInit(rank_active)
  val wantREF    = RegInit(false.B)
  val refsbBank  = RegInit(0.U(key.bankBits.W))

  (Seq(nextLegalPRE, nextLegalACT, nextLegalCASR, nextLegalCASW, nextLegalREFSB) ++
    bgNextLegalCASR ++ bgNextLegalCASW ++ bgNextLegalACT).foreach { mod =>
    mod.io.decr      := true.B
    mod.io.set.valid := false.B
    mod.io.set.bits  := DontCare
  }

  // tFAW: at most 4 activates per PC in any tFAW window. REFSB commands
  // count toward the window (JESD235).
  val actLike   = io.rowCmdUsesThisPC && (io.rowCmd === cmd_act || io.rowCmd === cmd_refsb)
  val tFAWcheck = Module(new Queue(io.tCycle.cloneType, entries = 4))
  tFAWcheck.io.enq.valid := actLike
  tFAWcheck.io.enq.bits  := io.tCycle + t.tFAW
  tFAWcheck.io.deq.ready := io.tCycle === tFAWcheck.io.deq.bits

  // ------------------------------------------------------------------
  // Column-bus command effects (CASR / CASW)
  // ------------------------------------------------------------------
  when(io.colCmdUsesThisPC && io.colCmd === cmd_casr) {
    assert(io.pc.canCASR, "HBM PC Timing Violation: Controller issued CASR command illegally")
    // RD-to-RD: tCCDS across groups, tCCDL within the group
    nextLegalCASR.io.set.valid := true.B
    nextLegalCASR.io.set.bits  := t.tCCDS - 1.U
    // RD-to-WR turnaround, PC scope (JESD235): nCL + nBL + 2 - nCWL
    nextLegalCASW.io.set.valid := true.B
    nextLegalCASW.io.set.bits  := t.tCAS + t.tBL + 2.U - t.tCWD - 1.U
    bgNextLegalCASR.zip(io.colBankGroupOH.asBools).foreach { case (bg, sel) =>
      when(sel) {
        bg.io.set.valid := true.B
        bg.io.set.bits  := t.tCCDL - 1.U
      }
    }
    bgNextLegalCASW.zip(io.colBankGroupOH.asBools).foreach { case (bg, sel) =>
      when(sel) {
        bg.io.set.valid := true.B
        bg.io.set.bits  := t.tCCDL - 1.U
      }
    }
  }.elsewhen(io.colCmdUsesThisPC && io.colCmd === cmd_casw) {
    assert(io.pc.canCASW, "HBM PC Timing Violation: Controller issued CASW command illegally")
    // WR-to-WR: tCCDS across groups, tCCDL within the group
    nextLegalCASW.io.set.valid := true.B
    nextLegalCASW.io.set.bits  := t.tCCDS - 1.U
    // WR-to-RD turnaround: tWTRS across groups, tWTRL within the group
    nextLegalCASR.io.set.valid := true.B
    nextLegalCASR.io.set.bits  := t.tCWD + t.tBL + t.tWTRS - 1.U
    bgNextLegalCASR.zip(io.colBankGroupOH.asBools).foreach { case (bg, sel) =>
      when(sel) {
        bg.io.set.valid := true.B
        bg.io.set.bits  := t.tCWD + t.tBL + t.tWTRL - 1.U
      }
    }
    bgNextLegalCASW.zip(io.colBankGroupOH.asBools).foreach { case (bg, sel) =>
      when(sel) {
        bg.io.set.valid := true.B
        bg.io.set.bits  := t.tCCDL - 1.U
      }
    }
  }

  // ------------------------------------------------------------------
  // Row-bus command effects (ACT / PRE / REF / REFSB)
  // ------------------------------------------------------------------
  when(io.rowCmdUsesThisPC) {
    switch(io.rowCmd) {
      is(cmd_act) {
        assert(io.pc.canACT, "HBM PC Timing Violation: Controller issued ACT command illegally")
        // Different bank group: tRRDS; same bank group: tRRDL
        nextLegalACT.io.set.valid := true.B
        nextLegalACT.io.set.bits  := t.tRRDS - 1.U
        // ACT-to-REFSB spacing (tRREFD)
        nextLegalREFSB.io.set.valid := true.B
        nextLegalREFSB.io.set.bits  := t.tRREFD - 1.U
        bgNextLegalACT.zip(io.rowBankGroupOH.asBools).foreach { case (bg, sel) =>
          when(sel) {
            bg.io.set.valid := true.B
            bg.io.set.bits  := t.tRRDL - 1.U
          }
        }
      }
      is(cmd_pre) {
        assert(io.pc.canPRE, "HBM PC Timing Violation: Controller issued PRE command illegally")
      }
      is(cmd_ref) {
        assert(io.pc.canREF, "HBM PC Timing Violation: Controller issued REF command illegally")
        wantREF                   := false.B
        state                     := rank_refresh
        nextLegalACT.io.set.valid := true.B
        nextLegalACT.io.set.bits  := t.tRFC - 1.U
      }
      is(cmd_refsb) {
        assert(io.pc.canREFSB, "HBM PC Timing Violation: Controller issued REFSB command illegally")
        wantREF   := false.B
        refsbBank := refsbBank + 1.U
        // REFSB-to-REFSB and REFSB-to-ACT spacing (tRREFD)
        nextLegalREFSB.io.set.valid := true.B
        nextLegalREFSB.io.set.bits  := t.tRREFD - 1.U
        nextLegalACT.io.set.valid   := true.B
        nextLegalACT.io.set.bits    := t.tRREFD - 1.U
      }
    }
  }

  // Refresh scheduling. In REFab mode one refresh is owed per tREFI; in
  // REFSB mode one (single-bank) refresh is owed per tREFI / maxBanks.
  // Disable refresh by setting tREFI = 0.
  val refInterval = Mux(io.perBankRefresh, t.tREFI >> key.bankBits, t.tREFI)
  when(refCounter >= refInterval && t.tREFI =/= 0.U) {
    refCounter := 0.U
    wantREF    := true.B
  }.otherwise {
    refCounter := refCounter + 1.U
  }

  when(state === rank_refresh && nextLegalACT.io.current === 1.U) {
    state := rank_active
  }

  val bankTrackers = Seq.fill(key.maxBanks)(Module(new HBMBankStateTracker(key)).io)
  io.pc.banks.zip(bankTrackers).foreach { case (out, bank) => out := bank.out }

  bankTrackers.zipWithIndex.foreach { case (bank, i) =>
    val colHit = io.colCmdUsesThisPC && io.colBankOH(i)
    val rowHit = io.rowCmdUsesThisPC && io.rowBankOH(i)
    assert(
      !(colHit && rowHit && io.colCmd =/= cmd_nop && io.rowCmd =/= cmd_nop),
      "HBM PC Tracker: row and column commands targeted the same bank in the same cycle",
    )
    bank.timings         := t
    bank.selectedCmd     := Mux(colHit, io.colCmd, Mux(rowHit, io.rowCmd, cmd_nop))
    bank.cmdUsesThisBank := colHit || rowHit
    bank.cmdRow          := io.cmdRow
    bank.autoPRE         := io.autoPRE
  }

  val refsbBankCanACT = Mux1H(UIntToOH(refsbBank), bankTrackers.map { _.out.canACT })

  io.pc.canREF    := bankTrackers.map { _.out.canACT }.reduce { _ && _ }
  io.pc.canREFSB  := nextLegalREFSB.io.idle && refsbBankCanACT && tFAWcheck.io.enq.ready
  io.pc.refsbBank := refsbBank
  io.pc.canCASR   := nextLegalCASR.io.idle
  io.pc.canCASW   := nextLegalCASW.io.idle
  io.pc.canPRE    := nextLegalPRE.io.idle
  io.pc.canACT    := nextLegalACT.io.idle && tFAWcheck.io.enq.ready
  io.pc.wantREF   := wantREF
  io.pc.state     := state

  io.pc.bgCanCASR.zip(bgNextLegalCASR).foreach { case (out, ctr) => out := ctr.io.idle }
  io.pc.bgCanCASW.zip(bgNextLegalCASW).foreach { case (out, ctr) => out := ctr.io.idle }
  io.pc.bgCanACT.zip(bgNextLegalACT).foreach { case (out, ctr) => out := ctr.io.idle }
}

// ============================================================================
// The timing model
// ============================================================================

class HBMModelIO(val cfg: HBMModelConfig)(implicit p: Parameters) extends TimingModelIO()(p) {
  val mmReg = new HBMMMRegIO(cfg)
}

class HBMModel(cfg: HBMModelConfig)(implicit p: Parameters)
    extends TimingModel(cfg)(p)
    with HasDRAMMASConstants {

  val longName = "HBM2 Pseudo-Channel First-Ready FCFS MAS"
  def printTimingModelGenerationConfig: Unit = {}

  /** ************************** CHISEL BEGINS ********************************
    */
  import DRAMMasEnums._
  lazy val io = IO(new HBMModelIO(cfg))

  val timings = io.mmReg.hbmTimings
  val hbmKey  = cfg.hbmKey

  val backend          = Module(new DRAMBackend(p(NastiKey), cfg.backendKey))
  val xactionScheduler = Module(new UnifiedFIFOXactionScheduler(p(NastiKey), cfg.transactionQueueDepth, cfg))
  xactionScheduler.io.req          <> nastiReq
  xactionScheduler.io.pendingAWReq := pendingAWReq.value
  xactionScheduler.io.pendingWReq  := pendingWReq.value

  // Two command buses, per JESD235: one row command (ACT / PRE / REF /
  // REFSB) and one column command (CASR / CASW) may issue each cycle.
  val selectedRowCmd = WireInit(cmd_nop)
  val selectedColCmd = WireInit(cmd_nop)

  val pcStateTrackers = Seq.fill(hbmKey.maxPseudoChannels)(Module(new HBMPseudoChannelStateTracker(hbmKey)))

  // Presence bit per (PC, bank): prevents closing a row that still has ready entries
  val bankHasReadyEntries = RegInit(
    VecInit(Seq.fill(hbmKey.maxPseudoChannels * hbmKey.maxBanks)(false.B))
  )

  val newReference = Wire(Decoupled(new HBMEntry(p(NastiKey), cfg)))
  newReference.valid := xactionScheduler.io.nextXaction.valid
  newReference.bits.decode(xactionScheduler.io.nextXaction.bits, io.mmReg)

  val rowHitsInPC = VecInit(pcStateTrackers.map { tracker =>
    VecInit(tracker.io.pc.banks.map { _.isRowHit(newReference.bits) }).asUInt
  })

  xactionScheduler.io.nextXaction.ready := newReference.ready

  val refBuffer  = CollapsingBuffer(
    enq               = newReference,
    depth             = cfg.schedulerWindowSize,
    programmableDepth = Some(io.mmReg.schedulerWindowSize),
  )
  val refList    = refBuffer.io.entries
  val refUpdates = refBuffer.io.updates

  val columnArbiter = Module(new Arbiter(refList.head.bits.cloneType, refList.size))

  // Legality of a command for an entry = bank legal && bank-group legal && PC legal
  def checkLegality(
    getBankField: HBMBankStateTrackerO => Bool,
    getBGField:   HBMPseudoChannelStateTrackerO => Vec[Bool],
    getPCField:   HBMPseudoChannelStateTrackerO => Bool,
  )(entry: HBMEntry): Bool = {
    val bankFields = pcStateTrackers.map { pc => VecInit(pc.io.pc.banks.map(getBankField)).asUInt }
    val bankLegal  = (Mux1H(entry.pcAddrOH, bankFields) & entry.bankAddrOH).orR
    val bgFields   = pcStateTrackers.map { pc => getBGField(pc.io.pc).asUInt }
    val bgLegal    = (Mux1H(entry.pcAddrOH, bgFields) & entry.bankGroupAddrOH).orR
    val pcFields   = VecInit(pcStateTrackers.map { pc => getPCField(pc.io.pc) }).asUInt
    val pcLegal    = (entry.pcAddrOH & pcFields).orR
    bankLegal && bgLegal && pcLegal
  }

  def pcWantsRef(pcAddrOH: UInt): Bool =
    (pcAddrOH & (VecInit(pcStateTrackers.map { _.io.pc.wantREF }).asUInt)).orR

  val canLegallyCASR = checkLegality(_.canCASR, _.bgCanCASR, _.canCASR) _
  val canLegallyCASW = checkLegality(_.canCASW, _.bgCanCASW, _.canCASW) _
  val canLegallyACT  = checkLegality(_.canACT, _.bgCanACT, _.canACT) _
  // PRE has no bank-group-scope constraint
  val canLegallyPRE  = checkLegality(_.canPRE, o => VecInit(Seq.fill(hbmKey.maxBankGroups)(true.B)), _.canPRE) _

  // ------------------------------------------------------------------
  // Column bus: issue a legal CAS whenever the arbiter offers one
  // ------------------------------------------------------------------
  columnArbiter.io.in <> refList.map({ entry =>
    val candidate = V2D(entry)
    val canCASR   = canLegallyCASR(entry.bits) && backend.io.newRead.ready
    val canCASW   = canLegallyCASW(entry.bits) && backend.io.newWrite.ready
    candidate.valid := entry.valid && entry.bits.isReady &&
      Mux(entry.bits.xaction.isWrite, canCASW, canCASR) &&
      !pcWantsRef(entry.bits.pcAddrOH)

    candidate
  })

  val colValid = columnArbiter.io.out.valid
  val colPC    = columnArbiter.io.out.bits.pcAddr
  val colBank  = columnArbiter.io.out.bits.bankAddr
  when(colValid) {
    selectedColCmd := Mux(columnArbiter.io.out.bits.xaction.isWrite, cmd_casw, cmd_casr)
  }
  columnArbiter.io.out.ready := true.B

  val memReqDone = (selectedColCmd === cmd_casr || selectedColCmd === cmd_casw)

  // A row command may not target the bank the column bus is using this cycle
  def conflictsWithCol(pc: UInt, bank: UInt): Bool = colValid && pc === colPC && bank === colBank

  // ------------------------------------------------------------------
  // Row bus: REF/REFSB > refresh-prep PRE > ACT > PRE. An ACT occupies the
  // row bus for two cycles (JESD235 two-frame ACT encoding).
  // ------------------------------------------------------------------
  val rowBusBusy = RegNext(selectedRowCmd === cmd_act, false.B)

  val entryWantsPRE = refList.map { ref =>
    ref.valid && ref.bits.wantPRE() && canLegallyPRE(ref.bits) &&
    !conflictsWithCol(ref.bits.pcAddr, ref.bits.bankAddr)
  }
  val entryWantsACT = refList.map { ref =>
    ref.valid && ref.bits.wantACT() && canLegallyACT(ref.bits) &&
    !pcWantsRef(ref.bits.pcAddrOH)
  }

  val preBank    = PriorityMux(entryWantsPRE, refList.map(_.bits.bankAddr))
  val prePC      = PriorityMux(entryWantsPRE, refList.map(_.bits.pcAddr))
  val suggestPre = entryWantsPRE.reduce { _ || _ }

  val actPC   = PriorityMux(entryWantsACT, refList.map(_.bits.pcAddr))
  val actBank = PriorityMux(entryWantsACT, refList.map(_.bits.bankAddr))
  val actRow  = PriorityMux(entryWantsACT, refList.map(_.bits.rowAddr))

  val suggestAct = (entryWantsACT
    .zip(entryWantsPRE))
    .foldRight(false.B)({ case ((act, pre), current) =>
      Mux(act, true.B, !pre && current)
    })

  val rowPC   = WireInit(UInt(hbmKey.pcBits.W), init = prePC)
  val rowBank = WireInit(UInt(hbmKey.bankBits.W), init = preBank)
  val cmdRow  = actRow

  val perBankRefresh    = io.mmReg.perBankRefresh
  val pcsInUse          = io.mmReg.pcAddr.maskToOH()
  val pcsWantingRefresh = VecInit(pcStateTrackers.map { _.io.pc.wantREF }).asUInt

  // --- All-bank refresh (REFab) arbitration ---
  val refreshablePCs = VecInit(pcStateTrackers.map { _.io.pc.canREF }).asUInt & pcsInUse
  val refRefPC       = PriorityEncoder(pcsWantingRefresh & refreshablePCs)
  val suggestREF     = !perBankRefresh && (pcsWantingRefresh & refreshablePCs).orR
  // Precharge banks in preparation of an all-bank refresh
  val preRefBanks      = pcStateTrackers.map { pc => PriorityEncoder(pc.io.pc.banks.map { _.canPRE }) }
  val prechargeablePCs = VecInit(pcStateTrackers.map { pc =>
    pc.io.pc.canPRE && (pc.io.pc.banks.map { _.canPRE }.reduce { _ || _ })
  }).asUInt & pcsInUse
  val refPrePC         = PriorityEncoder(pcsWantingRefresh & prechargeablePCs)
  val refPreBank       = PriorityMux(pcsWantingRefresh & prechargeablePCs, preRefBanks)
  val suggestRefPRE    = !perBankRefresh && (pcsWantingRefresh & prechargeablePCs).orR &&
    !conflictsWithCol(refPrePC, refPreBank)

  // --- Per-bank refresh (REFSB) arbitration ---
  val refsbReadyPCs   = VecInit(pcStateTrackers.map { pc =>
    pc.io.pc.wantREF && pc.io.pc.canREFSB
  }).asUInt & pcsInUse
  val refsbPC         = PriorityEncoder(refsbReadyPCs)
  val refsbBankSel    = PriorityMux(refsbReadyPCs, pcStateTrackers.map(_.io.pc.refsbBank))
  val suggestREFSB    = perBankRefresh && refsbReadyPCs.orR
  // Precharge the refresh-pending bank if it is currently active
  val refsbPrePCs     = VecInit(pcStateTrackers.map { pc =>
    pc.io.pc.wantREF && pc.io.pc.canPRE &&
    Mux1H(UIntToOH(pc.io.pc.refsbBank), pc.io.pc.banks.map(_.canPRE))
  }).asUInt & pcsInUse
  val refsbPrePC      = PriorityEncoder(refsbPrePCs)
  val refsbPreBank    = PriorityMux(refsbPrePCs, pcStateTrackers.map(_.io.pc.refsbBank))
  val suggestRefsbPRE = perBankRefresh && refsbPrePCs.orR &&
    !conflictsWithCol(refsbPrePC, refsbPreBank)

  when(!rowBusBusy) {
    when(suggestREF) {
      selectedRowCmd := cmd_ref
      rowPC          := refRefPC
    }.elsewhen(suggestREFSB) {
      selectedRowCmd := cmd_refsb
      rowPC          := refsbPC
      rowBank        := refsbBankSel
    }.elsewhen(suggestRefPRE) {
      selectedRowCmd := cmd_pre
      rowPC          := refPrePC
      rowBank        := refPreBank
    }.elsewhen(suggestRefsbPRE) {
      selectedRowCmd := cmd_pre
      rowPC          := refsbPrePC
      rowBank        := refsbPreBank
    }.elsewhen(suggestAct) {
      selectedRowCmd := cmd_act
      rowPC          := actPC
      rowBank        := actBank
    }.elsewhen(suggestPre) {
      selectedRowCmd := cmd_pre
      rowPC          := prePC
      rowBank        := preBank
    }
  }

  // ------------------------------------------------------------------
  // Scheduler-window bookkeeping
  // ------------------------------------------------------------------
  val entriesStillReady = refUpdates.zip(columnArbiter.io.in).map { case (ref, sel) =>
    when(sel.fire) { ref.valid := false.B }
    !sel.fire && ref.valid && ref.bits.isReady &&
    colBank === ref.bits.bankAddr && colPC === ref.bits.pcAddr
  }

  val otherReadyEntries = entriesStillReady.reduce { _ || _ }
  val casAutoPRE        = Mux(io.mmReg.openPagePolicy, false.B, memReqDone && !otherReadyEntries)

  refUpdates.foreach({ ref =>
    // Row-bus effects on pending references
    when(rowPC === ref.bits.pcAddr && rowBank === ref.bits.bankAddr) {
      when(selectedRowCmd === cmd_act) {
        ref.bits.isReady := ref.bits.rowAddr === cmdRow
        ref.bits.mayPRE  := false.B
      }.elsewhen(selectedRowCmd === cmd_pre) {
        ref.bits.isReady := false.B
        ref.bits.mayPRE  := false.B
      }
    }
    // Column-bus effects on pending references
    when(colPC === ref.bits.pcAddr && colBank === ref.bits.bankAddr) {
      when(memReqDone && !otherReadyEntries) {
        ref.bits.mayPRE := true.B
      }
    }
  })

  val newRefColBankMatch = newReference.bits.addrMatch(colPC, colBank)
  val newRefRowActMatch  = newReference.bits.addrMatch(rowPC, rowBank, Some(cmdRow))
  val newRefRowBankMatch = newReference.bits.addrMatch(rowPC, rowBank)
  newReference.bits.isReady :=
    selectedRowCmd === cmd_act && newRefRowActMatch ||
      (rowHitsInPC(newReference.bits.pcAddr) & newReference.bits.bankAddrOH).orR &&
      !(memReqDone && casAutoPRE && newRefColBankMatch) &&
      !(selectedRowCmd === cmd_pre && newRefRowBankMatch)

  newReference.bits.mayPRE :=
    Mux(
      io.mmReg.openPagePolicy,
      newRefColBankMatch && memReqDone && !otherReadyEntries ||
        !bankHasReadyEntries(Cat(newReference.bits.pcAddr, newReference.bits.bankAddr)) &&
        !(selectedRowCmd === cmd_pre && newRefRowBankMatch),
      false.B,
    )

  when(memReqDone) {
    bankHasReadyEntries(Cat(colPC, colBank)) := otherReadyEntries
  }
  when(selectedRowCmd === cmd_act) {
    bankHasReadyEntries(Cat(rowPC, rowBank)) := true.B
  }

  when(newReference.bits.isReady & newReference.fire) {
    bankHasReadyEntries(Cat(newReference.bits.pcAddr, newReference.bits.bankAddr)) := true.B
  }

  val rowPCOH        = UIntToOH(rowPC)
  val colPCOH        = UIntToOH(colPC)
  val rowBankOH      = UIntToOH(rowBank)
  val colBankOH      = UIntToOH(colBank)
  val rowBankGroupOH = UIntToOH(rowBank(hbmKey.bankGroupBits - 1, 0))
  val colBankGroupOH = UIntToOH(colBank(hbmKey.bankGroupBits - 1, 0))

  pcStateTrackers.zipWithIndex.foreach { case (tracker, i) =>
    tracker.io.rowCmd           := selectedRowCmd
    tracker.io.colCmd           := selectedColCmd
    tracker.io.rowCmdUsesThisPC := rowPCOH(i) && selectedRowCmd =/= cmd_nop
    tracker.io.colCmdUsesThisPC := colPCOH(i) && selectedColCmd =/= cmd_nop
    tracker.io.rowBankOH        := rowBankOH
    tracker.io.colBankOH        := colBankOH
    tracker.io.rowBankGroupOH   := rowBankGroupOH
    tracker.io.colBankGroupOH   := colBankGroupOH
    tracker.io.cmdRow           := cmdRow
    tracker.io.autoPRE          := casAutoPRE
    tracker.io.perBankRefresh   := perBankRefresh

    tracker.io.timings := timings
    tracker.io.tCycle  := tCycle
  }

  backend.io.tCycle        := tCycle
  backend.io.newRead.bits  := ReadResponseMetaData(p(NastiKey), columnArbiter.io.out.bits.xaction)
  backend.io.newRead.valid := memReqDone && !columnArbiter.io.out.bits.xaction.isWrite
  backend.io.readLatency   := timings.tCAS + io.mmReg.backendLatency

  // Writes are acknowledged immediately once issued
  backend.io.newWrite.bits  := WriteResponseMetaData(p(NastiKey), columnArbiter.io.out.bits.xaction)
  backend.io.newWrite.valid := memReqDone && columnArbiter.io.out.bits.xaction.isWrite
  backend.io.writeLatency   := 1.U

  wResp <> backend.io.completedWrite
  rResp <> backend.io.completedRead

  // Dump both command streams (pseudo channel printed in the rank position).
  // Row bus: activate / precharge / refresh / refsb; column bus: read / write.
  val rowCmdMonitor = Module(new CommandBusMonitor())
  rowCmdMonitor.io.cmd     := selectedRowCmd
  rowCmdMonitor.io.rank    := rowPC
  rowCmdMonitor.io.bank    := rowBank
  rowCmdMonitor.io.row     := cmdRow
  rowCmdMonitor.io.autoPRE := false.B

  val colCmdMonitor = Module(new CommandBusMonitor())
  colCmdMonitor.io.cmd     := selectedColCmd
  colCmdMonitor.io.rank    := colPC
  colCmdMonitor.io.bank    := colBank
  colCmdMonitor.io.row     := 0.U
  colCmdMonitor.io.autoPRE := casAutoPRE
}
