package toolchain

import chisel3._
import chiseltest._
import org.scalatest.flatspec.AnyFlatSpec

class PassThrough extends Module {
  val io = IO(new Bundle {
    val a = Input(Bool())
    val b = Output(Bool())
  })
  io.b := io.a
}

class ToolchainSpec extends AnyFlatSpec with ChiselScalatestTester {
  "chisel" should "simulate a wire" in {
    test(new PassThrough) { dut =>
      dut.io.a.poke(true.B)
      dut.clock.step()
      dut.io.b.expect(true.B)
    }
  }
}
