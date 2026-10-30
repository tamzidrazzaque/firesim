

// AXI4 fuzzer against the HyperRAM timing model.
class HyperRAMF2Config
    extends Config(
      new HyperRAM32MB ++
        new midas.F2Config
    )

class HyperRAMF2ReqTraceConfig
    extends Config(
      new WithHyperRAMRequestTrace ++
        new HyperRAMF2Config
    )

// AXI4 fuzzer against the RPC DRAM timing model.
class RpcDramF2Config
    extends Config(
      new RpcDram256Mb ++
        new midas.F2Config
    )

class RpcDramF2ReqTraceConfig
    extends Config(
      new WithRpcDramRequestTrace ++
        new RpcDramF2Config
    )

class IndRpcDramF2Config
    extends Config(
      new IndRpcDram256Mb ++
        new midas.F2Config
    )

class IndRpcDramF2ReqTraceConfig
    extends Config(
      new WithIndRpcDramRequestTrace ++
        new IndRpcDramF2Config
    )
