package chipyard

import org.chipsalliance.cde.config.Config

class RpcRocketConfig extends Config(
  new chipyard.harness.WithRpcPinMem ++
  new freechips.rocketchip.subsystem.WithExtMemSize(32L << 20) ++
  new chipyard.config.WithUniformBusFrequencies(200.0) ++
  new chipyard.RocketConfig)

class RpcBoomConfig extends Config(
  new chipyard.harness.WithRpcPinMem ++
  new freechips.rocketchip.subsystem.WithExtMemSize(32L << 20) ++
  new chipyard.config.WithUniformBusFrequencies(200.0) ++
  new chipyard.LargeBoomV3Config)
