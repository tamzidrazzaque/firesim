

// HyperRAM (S80KS2562-class) and RPC DRAM timing models. Timings are runtime
// registers; the defaults match the Python reference profiles.
class WithHyperRAM
    extends Config((site, _, _) => { case MemModelKey =>
      new HyperRAMModelConfig(
        params       = site(BaseParamsKey),
        requestTrace = false,
      )
    })

class WithHyperRAMRequestTrace
    extends Config((_, _, up) => { case MemModelKey =>
      up(MemModelKey) match {
        case model: HyperRAMModelConfig => model.copy(requestTrace = true)
        case other                      =>
          throw new IllegalArgumentException(
            s"WithHyperRAMRequestTrace requires a HyperRAMModelConfig, got: ${other.getClass.getName}"
          )
      }
    })

class HyperRAM32MB
    extends Config(
      new WithFuncModelLimits(32, 32) ++
        new WithHyperRAM ++
        new WithDefaultMemModel
    )

class WithRpcDram
    extends Config((site, _, _) => { case MemModelKey =>
      new RpcDramModelConfig(
        params       = site(BaseParamsKey),
        requestTrace = false,
      )
    })

class WithRpcDramRequestTrace
    extends Config((_, _, up) => { case MemModelKey =>
      up(MemModelKey) match {
        case model: RpcDramModelConfig => model.copy(requestTrace = true)
        case other                     =>
          throw new IllegalArgumentException(
            s"WithRpcDramRequestTrace requires a RpcDramModelConfig, got: ${other.getClass.getName}"
          )
      }
    })

class RpcDram256Mb
    extends Config(
      new WithFuncModelLimits(32, 32) ++
        new WithRpcDram ++
        new WithDefaultMemModel
    )

class WithIndRpcDram
    extends Config((site, _, _) => { case MemModelKey =>
      new IndRpcDramModelConfig(
        params       = site(BaseParamsKey),
        requestTrace = false,
      )
    })

class WithIndRpcDramRequestTrace
    extends Config((_, _, up) => { case MemModelKey =>
      up(MemModelKey) match {
        case model: IndRpcDramModelConfig => model.copy(requestTrace = true)
        case other                        =>
          throw new IllegalArgumentException(
            s"WithIndRpcDramRequestTrace requires an IndRpcDramModelConfig, got: ${other.getClass.getName}"
          )
      }
    })

class IndRpcDram256Mb
    extends Config(
      new WithFuncModelLimits(32, 32) ++
        new WithIndRpcDram ++
        new WithDefaultMemModel
    )
