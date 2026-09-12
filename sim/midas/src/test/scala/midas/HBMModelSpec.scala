// See LICENSE for license details.

package goldengate.tests

import org.scalatest.flatspec.AnyFlatSpec

import org.chipsalliance.cde.config.{Config, Parameters}

import junctions.NastiKey
import firesim.lib.nasti.NastiParameters
import midas.models._

/** Elaborates the FASED HBM2 timing model (and the DDR3 FR-FCFS model as a
  * control) to catch hardware construction errors: width mismatches, invalid
  * connections, unassigned wires, etc.
  */
class HBMModelSpec extends AnyFlatSpec with ElaborationUtils {

  implicit val p: Parameters = new Config((_, _, _) => { case NastiKey =>
    NastiParameters(dataBits = 64, addrBits = 32, idBits = 4)
  })

  def baseParams = BaseParams(maxReads = 16, maxWrites = 16)

  def hbmConfig = HBMModelConfig(
    hbmKey                = HBMOrganizationParams(
      maxPseudoChannels = 2,
      maxBankGroups     = 4,
      banksPerGroup     = 4,
      channelSize       = BigInt(1) << 34,
    ),
    schedulerWindowSize   = 8,
    transactionQueueDepth = 8,
    params                = baseParams,
  )

  def frfcfsConfig = FirstReadyFCFSConfig(
    dramKey               = DramOrganizationParams(maxBanks = 8, maxRanks = 4, dramSize = BigInt(1) << 34),
    schedulerWindowSize   = 8,
    transactionQueueDepth = 8,
    params                = baseParams,
  )

  behavior.of("FirstReadyFCFSModel (control)")

  it should "elaborate and lower to Verilog" in {
    elaborateAndLower(new FirstReadyFCFSModel(frfcfsConfig))
  }

  behavior.of("HBMModel")

  it should "elaborate and lower to Verilog" in {
    elaborateAndLower(new HBMModel(hbmConfig))
  }

  it should "elaborate and lower to Verilog with four channels" in {
    elaborateAndLower(
      new HBMModel(hbmConfig.copy(hbmKey = hbmConfig.hbmKey.copy(maxChannels = 4), requestTrace = true))
    )
  }

  it should "have complete HBM2 timing tables" in {
    val timings = new HBMProgrammableTimings()
    val fields  = timings.registers.map { case (elem, _) => timings.getName(elem) }.toSet
    for ((table, name) <- HBMTimingTables.grades) {
      assert(
        fields.subsetOf(table.keySet) && table.keySet.subsetOf(fields),
        s"Timing table '${name}' keys must exactly match HBMProgrammableTimings fields",
      )
    }
  }
}
