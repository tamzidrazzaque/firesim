// Legal ACT-then-RD after tRCD returns the written byte.
// An immediate RD is an error. This is a command-level device test, not
// the ETH PHY.
`timescale 1ns/1ps

module tb_rpc_array;
  logic clk = 0;
  logic rst_n = 0;
  always #5 clk = ~clk;

  logic        cmd_valid, cmd_ready, resp_valid, error;
  logic [3:0]  cmd_op;
  logic [1:0]  cmd_bank;
  logic [11:0] cmd_row;
  logic [7:0]  cmd_wdata, resp_rdata;
  int errors;
  int i;

  rpc_array dut (
    .clk, .rst_n, .cmd_valid, .cmd_ready, .cmd_op, .cmd_bank, .cmd_row,
    .cmd_wdata, .resp_valid, .resp_rdata, .error
  );

  task automatic tick;
    begin
      @(posedge clk);
      #1;
    end
  endtask

  initial begin
    errors = 0;
    cmd_valid = 0;
    cmd_op = 0;
    cmd_bank = 0;
    cmd_row = 0;
    cmd_wdata = 0;
    repeat (2) tick();
    rst_n = 1;
    tick();

    // Read of a closed bank must be flagged.
    cmd_valid = 1;
    cmd_op = 4'd6;
    tick();
    cmd_valid = 0;
    if (!error) begin
      $display("FAIL closed-bank read was accepted");
      errors = errors + 1;
    end else $display("PASS closed-bank read");

    // ACT row 5, write, then read one cycle later (tRCD = 11).
    cmd_valid = 1;
    cmd_op = 4'd4;
    cmd_row = 12'd5;
    tick();
    cmd_op = 4'd5;
    cmd_wdata = 8'h3C;
    tick();
    cmd_valid = 0;
    if (!error) begin
      $display("FAIL early write was not flagged");
      errors = errors + 1;
    end else $display("PASS tRCD write");

    cmd_valid = 1;
    cmd_op = 4'd4;
    cmd_row = 12'd5;
    tick();
    cmd_valid = 0;
    // Age increments while open. Wait 11 cycles, then write and read.
    for (i = 0; i < 11; i++) tick();
    cmd_valid = 1;
    cmd_op = 4'd5;
    cmd_wdata = 8'h3C;
    tick();
    cmd_op = 4'd6;
    tick();
    cmd_valid = 0;
    if (error || resp_rdata !== 8'h3C) begin
      $display("FAIL data=%h error=%b", resp_rdata, error);
      errors = errors + 1;
    end else $display("PASS read-after-write");

    if (errors == 0) begin
      $display("ALL PASS");
      $finish;
    end else begin
      $display("FAILED %0d", errors);
      $fatal(1);
    end
  end
endmodule
