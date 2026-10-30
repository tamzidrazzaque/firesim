package chipyard.harness

import chisel3._
import chisel3.experimental.IntParam
import chisel3.util.HasBlackBoxResource
import freechips.rocketchip.amba.axi4.{AXI4Bundle, AXI4BundleParameters}
import freechips.rocketchip.subsystem._
import chipyard.iobinders._

class SimRPC(params: AXI4BundleParameters, memBase: BigInt) extends BlackBox(Map(
  "ADDR_BITS" -> IntParam(params.addrBits),
  "DATA_BITS" -> IntParam(params.dataBits),
  "ID_BITS" -> IntParam(params.idBits),
  "MEM_BASE" -> IntParam(memBase)
)) with HasBlackBoxResource {
  require(params.dataBits == 64, "ETH RPC controller has a 64-bit AXI port")
  require(params.idBits <= 6, "ETH RPC controller has at most six AXI ID bits")
  val io = IO(new Bundle {
    val clock = Input(Clock())
    val reset = Input(Reset())
    val axi = Flipped(new AXI4Bundle(params))
  })
  addResource("/chipyard/vsrc/SimRPC.v")
}

class WithRpcPinMem extends HarnessBinder({
  case (th: HasHarnessInstantiators, port: AXI4MemPort, chipId: Int) => {
    val mem = Module(new SimRPC(port.edge.bundle, port.params.master.base)).suggestName("simrpc")
    mem.io.clock := port.io.clock
    mem.io.reset := th.harnessBinderReset.asAsyncReset
    mem.io.axi <> port.io.bits
  }
})
