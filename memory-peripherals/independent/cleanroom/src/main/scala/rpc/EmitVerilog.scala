package rpc

import scala.annotation.nowarn

import java.nio.charset.StandardCharsets
import java.nio.file.{Files, Paths}

/** `sbt "runMain rpc.EmitVerilog [output.v]"`, default generated/RpcTimingChecker.v. */
object EmitVerilog {
  // chisel3.stage.ChiselStage is the Verilog path that ships with Chisel 3.6
  // without an external firtool binary.
  @nowarn("cat=deprecation")
  def main(args: Array[String]): Unit = {
    val out = Paths.get(args.headOption.getOrElse("generated/RpcTimingChecker.v"))
    val verilog = (new chisel3.stage.ChiselStage)
      .emitVerilog(new RpcTimingChecker(), Array("--target-dir", "target/emit-verilog"))
    Option(out.getParent).foreach(Files.createDirectories(_))
    Files.write(out, verilog.getBytes(StandardCharsets.UTF_8))
    println(s"wrote $out")
  }
}
