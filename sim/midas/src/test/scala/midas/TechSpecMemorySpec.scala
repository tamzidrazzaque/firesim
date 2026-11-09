// See LICENSE for license details.

package goldengate.tests

import org.scalatest.flatspec.AnyFlatSpec

import org.chipsalliance.cde.config.{Config, Parameters}

import junctions.NastiKey
import firesim.lib.nasti.NastiParameters
import midas.models._

/** Elaborates the technology-spec memory and checks that the HBM config key
  * still builds an HBM model. This does not simulate cycles; the cycle rules
  * are checked by sim/scripts/emerging-memory/test_techspec.py.
  */
class TechSpecMemorySpec extends AnyFlatSpec with ElaborationUtils {

  implicit val p: Parameters = new Config((_, _, _) => { case NastiKey =>
    NastiParameters(dataBits = 64, addrBits = 32, idBits = 4)
  })

  def baseParams = BaseParams(maxReads = 16, maxWrites = 16, beatCounters = true)

  def techConfig = TechSpecMemoryConfig(
    params                    = baseParams,
    retentionSets             = 64,
    retentionGranularityBytes = 64,
    requestTrace              = true,
  )

  behavior.of("TechSpecMemoryModel")

  it should "elaborate and lower to Verilog with the retention monitor and trace" in {
    elaborateAndLower(new TechSpecMemoryModel(techConfig))
  }

  it should "elaborate with the retention monitor disabled" in {
    elaborateAndLower(new TechSpecMemoryModel(techConfig.copy(retentionSets = 0, requestTrace = false)))
  }

  it should "expose the illustrative defaults and reject a zero service time at the register" in {
    val regs     = new TechSpecMMRegIO(techConfig)
    val defaults = regs.registers.map { case (elem, setting) => regs.getName(elem) -> setting }.toMap
    assert(defaults("readLatency").default == 30)
    assert(defaults("writeLatency").default == 30)
    assert(defaults("readServiceCycles").default == 1)
    assert(defaults("readServiceCycles").min == 1)
    assert(defaults("writeServiceCycles").min == 1)
    assert(defaults("enduranceLimitBytes").default == 0)
    assert(defaults("retentionCycles").default == 0)
    assert(defaults("traceEnable").default == 0)
    assert(defaults("readMaxReqs").default == 16)
  }

  it should "keep the existing HBM2 platform config on HBMModelConfig" in {
    val mem = new firesim.configs.HBM2FRFCFS16GBDualPC().apply(firesim.configs.MemModelKey)
    assert(mem.isInstanceOf[HBMModelConfig])
    val hbm = mem.asInstanceOf[HBMModelConfig]
    assert(hbm.hbmKey.maxChannels == 1)
    assert(hbm.hbmKey.maxPseudoChannels == 2)
    assert(hbm.hbmKey.maxBanks == 16)
    assert(!hbm.requestTrace)
  }

  it should "select the technology-spec model from TechSpecByteNVM without tracing" in {
    val mem = new firesim.configs.TechSpecByteNVM().apply(firesim.configs.MemModelKey)
    assert(mem.isInstanceOf[TechSpecMemoryConfig])
    val tech = mem.asInstanceOf[TechSpecMemoryConfig]
    assert(tech.retentionSets == 64)
    assert(!tech.requestTrace)
    assert(tech.params.maxReads == 32 && tech.params.maxWrites == 32)
    assert(tech.params.beatCounters)
  }
}
