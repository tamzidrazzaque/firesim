`timescale 1ns/1ps

// Pin-packet contract test for the standalone RPC observer. Shortened reset,
// ZQ, and array dimensions keep the protocol boundary cases fast; the ETH
// directed bench uses the real 200-MHz parameters and production controller.
module tb_rpc_timing_observe;
  logic clk = 0;
  always #2.5 clk = ~clk;
  logic rst_n = 0, cs_n = 1, stb = 1, db_oe = 0;
  logic [15:0] db = 0;
  rpc_timing_observe #(
    .ROWS(4), .TPOWERUP(0), .TRESET(4), .TZQINIT(8), .CASE_TEMP_GT85(1)
  ) dut (
    .clk_i(clk), .rst_ni(rst_n), .cs_ni(cs_n),
    .stb_i(stb), .db_i(db), .db_oe_i(db_oe)
  );

  task automatic packet_at(input int target, input logic [31:0] p);
    while (dut.cycle < target - 3) @(negedge clk);
    cs_n = 0;
    stb = 0;
    db_oe = 1;
    @(posedge clk);
    @(posedge clk);
    #0.1 db = p[31:16];
    @(posedge clk);
    #0.1 db = p[15:0];
    @(negedge clk);
    #0.1;
    cs_n = 1;
    stb = 1;
    db_oe = 0;
    if (dut.cycle != target)
      $fatal(1, "packet timing target=%0d actual=%0d", target, dut.cycle);
  endtask

  initial begin
    int t, v, old_rl, accepted;
    repeat (4) @(negedge clk);
    rst_n = 1;
    packet_at(10, 32'h00000001); // RESET
    packet_at(14, 32'h03c40000); // PRE ALL
    packet_at(18, 32'h04020000); // CL8, nWR4, output enabled
    packet_at(30, 32'h00010001); // ZQINIT
    packet_at(38, 32'h00050002); // ACT bank 0, row 1
    if (dut.violations != 0 || !dut.row_open[0])
      $fatal(1, "legal init/ACT rejected");

    // Active-bank tPPD is eight cycles; rejected CAS must not become history.
    t = dut.act_at[0];
    v = dut.violations;
    packet_at(t + 4, 32'h00000000); // RD one word, early
    if (dut.violations != v + 1 || dut.col_kind != 0 || dut.last_cmd != t)
      $fatal(1, "early RD was accepted or mutated state");
    v = dut.violations;
    packet_at(t + 8, 32'h00460000); // REF before ACT+tRC
    if (dut.violations != v + 1 || dut.refreshes != 0 || dut.last_cmd != t)
      $fatal(1, "early REF was accepted or mutated state");
    v = dut.violations;
    packet_at(t + 12, 32'h00000000);
    if (dut.violations != v + 1 || dut.col_kind != 0 || dut.last_cmd != t)
      $fatal(1, "off-grid RD was accepted or mutated state");
    v = dut.violations;
    packet_at(t + 16, 32'h00000000);
    if (dut.violations != v || dut.col_kind != 1)
      $fatal(1, "legal grid-aligned RD after rejected RDs failed");

    // Read data must complete before PRE of that bank. Rejected PRE leaves
    // the row open, and a later legal PRE closes it.
    t = dut.col_at;
    packet_at(t + 8, 32'h00460000); // REF before read data end
    if (dut.violations != v + 1 || dut.refreshes != 0 || !dut.row_open[0])
      $fatal(1, "REF before read data end was accepted");
    v = dut.violations;
    packet_at(t + 16, 32'h00440000);
    if (dut.violations != v + 1 || !dut.row_open[0])
      $fatal(1, "early PRE changed bank state");
    v = dut.violations;
    packet_at(t + 24, 32'h00440000);
    if (dut.violations != v || dut.row_open[0])
      $fatal(1, "legal PRE failed");

    // A reserved MRS CL code is reported without changing RL.
    old_rl = dut.rl;
    packet_at(dut.last_cmd + 4, 32'h041a0000);
    if (dut.violations != v + 1 || dut.rl != old_rl)
      $fatal(1, "reserved MRS changed mode");
    v = dut.violations;

    // One bank, four test rows, 20 CK per row: busy until REF+80.
    packet_at(dut.last_cmd + 8, 32'h00460000);
    accepted = dut.refreshes;
    t = dut.last_cmd;
    packet_at(t + 4, 32'h00050004);
    if (dut.violations != v + 1 || dut.row_open[0] || dut.refreshes != accepted)
      $fatal(1, "ACT during REF was accepted");
    v = dut.violations;
    packet_at(t + 80, 32'h00050004);
    if (dut.violations != v || !dut.row_open[0])
      $fatal(1, "ACT at exact REF end rejected");
    t = dut.act_at[0];
    packet_at(t + 8, 32'h00000000);
    if (dut.violations != v) $fatal(1, "CAS at exact active tPPD rejected");
    t = dut.col_at;
    packet_at(t + 24, 32'h00440000); // RL+burst ends at 17, next 8-CK slot is 24
    if (dut.violations != v || dut.row_open[0])
      $fatal(1, "PRE at exact read-data end rejected");

    packet_at(dut.last_cmd + 4, 32'h01c60002); // LP REF, three banks above 85C
    if (dut.violations != v + 1 || dut.refreshes != 1)
      $fatal(1, "high-temperature LP bank limit missed");
    v = dut.violations;
    packet_at(dut.last_cmd + 8, 32'h00060000); // no selected bank
    if (dut.violations != v + 1 || dut.refreshes != 1)
      $fatal(1, "empty REF bank mask accepted");

    $display("PASS rpc observer rejected=%0d accepted_refresh=%0d", dut.violations, dut.refreshes);
    $finish;
  end
endmodule
