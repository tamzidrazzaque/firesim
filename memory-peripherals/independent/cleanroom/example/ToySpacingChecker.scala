// Illustrative checker shape only.
// The numbers below are not taken from any memory datasheet.
// Do not copy them into the RPC DRAM model.

package example

import chisel3._
import chisel3.util._

class ToySpacingChecker extends Module {
  val io = IO(new Bundle {
    val valid = Input(Bool())
    val cycle = Input(UInt(64.W))
    val gap = Input(UInt(16.W))
    val accepted = Output(Bool())
    val earliest = Output(UInt(64.W))
  })
  val nextFree = RegInit(0.U(64.W))
  io.earliest := nextFree
  io.accepted := !io.valid || io.cycle >= nextFree
  when(io.valid && io.accepted) {
    nextFree := io.cycle + io.gap
  }
}
