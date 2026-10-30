`timescale 1ns/1ps

module tb_hyperram_pin;
  logic ck = 0, reset_n = 0, cs_n = 1;
  logic [7:0] dq_in = 0, dq_out;
  logic dq_host_oe = 0, dq_dev_oe;
  logic rwds_in = 0, rwds_host_oe = 0, rwds_out, rwds_dev_oe;
  logic collision = 0;
  hyperram_pin_memory #(.FATAL_ON_VIOLATION(0)) dut (
    .ck_i(ck), .reset_ni(reset_n), .cs_ni(cs_n),
    .dq_i(dq_in), .dq_oe_i(dq_host_oe), .rwds_i(rwds_in),
    .rwds_oe_i(rwds_host_oe), .force_refresh_collision_i(collision),
    .dq_o(dq_out), .dq_oe_o(dq_dev_oe),
    .rwds_o(rwds_out), .rwds_oe_o(rwds_dev_oe)
  );

  function automatic logic [47:0] make_ca(input bit rd, input bit reg_space,
                                           input bit linear, input int unsigned word);
    logic [28:0] upper;
    upper = 29'(word >> 3);
    return {rd, reg_space, linear, upper, 13'b0, word[2:0]};
  endfunction

  task automatic tick(input byte unsigned hi, input byte unsigned lo,
                      input bit drive_dq, input bit drive_rwds,
                      input bit mask_hi, input bit mask_lo,
                      output byte unsigned got_hi, output byte unsigned got_lo);
    dq_in = hi;
    dq_host_oe = drive_dq;
    rwds_host_oe = drive_rwds;
    rwds_in = mask_hi;
    #2.5 ck = 1;
    #0.001 got_hi = dq_out;
    dq_in = lo;
    rwds_in = mask_lo;
    #2.499 ck = 0;
    #0.001 got_lo = dq_out;
  endtask

  task automatic ca(input logic [47:0] cmd);
    byte unsigned x, y;
    tick(cmd[47:40], cmd[39:32], 1, 0, 0, 0, x, y);
    tick(cmd[31:24], cmd[23:16], 1, 0, 0, 0, x, y);
    tick(cmd[15:8], cmd[7:0], 1, 0, 0, 0, x, y);
  endtask

  task automatic idle_ck(input int count);
    byte unsigned x, y;
    repeat (count) tick(0, 0, 0, 0, 0, 0, x, y);
  endtask

  task automatic write_word(input int unsigned word, input byte unsigned hi,
                            input byte unsigned lo, input bit mask_lo,
                            input int latency);
    byte unsigned x, y;
    cs_n = 0;
    #4;
    ca(make_ca(0, 0, 1, word));
    idle_ck(latency);
    tick(hi, lo, 1, 1, 0, mask_lo, x, y);
    cs_n = 1;
  endtask

  task automatic read_word(input int unsigned word, input int latency,
                           output byte unsigned hi, output byte unsigned lo);
    cs_n = 0;
    #4;
    ca(make_ca(1, 0, 1, word));
    idle_ck(latency);
    tick(0, 0, 0, 0, 0, 0, hi, lo);
    if (!dq_dev_oe || !rwds_dev_oe) $fatal(1, "read pins not driven");
    cs_n = 1;
  endtask

  initial begin
    byte unsigned hi, lo;
    int v;
    #205 reset_n = 1;
    #205;

    write_word('h10, 8'ha1, 8'hb2, 0, 14);
    #6;
    read_word('h10, 14, hi, lo);
    if ({hi, lo} !== 16'ha1b2 || dut.violations != 0)
      $fatal(1, "fixed-latency readback %h %h violations=%0d", hi, lo, dut.violations);

    #35;
    write_word('h10, 8'hc3, 8'hd4, 1, 14);
    #6;
    read_word('h10, 14, hi, lo);
    if ({hi, lo} !== 16'hc3b2 || dut.violations != 0)
      $fatal(1, "RWDS mask readback %h %h violations=%0d", hi, lo, dut.violations);

    // A register write has zero initial latency and exactly one data word.
    #35;
    cs_n = 0;
    #4;
    ca(make_ca(0, 1, 1, 'h800));
    tick(8'h8f, 8'h27, 1, 0, 0, 0, hi, lo);
    cs_n = 1;
    if (dut.cr0 !== 16'h8f27 || dut.violations != 0)
      $fatal(1, "zero-latency CR0 write failed");

    #6;
    read_word('h10, 7, hi, lo);
    if ({hi, lo} !== 16'hc3b2 || dut.violations != 0)
      $fatal(1, "variable 1x read failed");
    #6;
    collision = 1;
    cs_n = 0;
    #0.001;
    if (!rwds_dev_oe || !rwds_out) $fatal(1, "collision RWDS CA high missing");
    #4;
    ca(make_ca(1, 0, 1, 'h10));
    collision = 0;
    idle_ck(14);
    tick(0, 0, 0, 0, 0, 0, hi, lo);
    cs_n = 1;
    if ({hi, lo} !== 16'hc3b2 || dut.violations != 0 || dut.collisions != 1)
      $fatal(1, "variable 2x read failed");

    // A register read repeats the selected 16-bit register while CS# stays low.
    #6;
    cs_n = 0;
    #4;
    ca(make_ca(1, 1, 1, 0));
    idle_ck(7);
    tick(0, 0, 0, 0, 0, 0, hi, lo);
    if ({hi, lo} !== 16'h0e86) $fatal(1, "ID0 read failed");
    tick(0, 0, 0, 0, 0, 0, hi, lo);
    cs_n = 1;
    if ({hi, lo} !== 16'h0e86 || dut.violations != 0)
      $fatal(1, "ID0 repeat failed");

    // One nanosecond before tCSHI is illegal; exactly 6 ns is legal.
    v = dut.violations;
    #5;
    read_word('h10, 7, hi, lo);
    if (dut.violations != v + 1) $fatal(1, "early tCSHI not detected");
    v = dut.violations;
    #6;
    read_word('h10, 7, hi, lo);
    if (dut.violations != v) $fatal(1, "exact tCSHI rejected");

    // The previous transaction was a read: 34 ns is one ns before tRWR.
    v = dut.violations;
    #34;
    write_word('h10, 8'h55, 8'h66, 0, 7);
    if (dut.violations != v + 1) $fatal(1, "early tRWR not detected");
    #6;
    read_word('h10, 7, hi, lo);
    v = dut.violations;
    #35;
    write_word('h10, 8'h77, 8'h88, 0, 7);
    if (dut.violations != v) $fatal(1, "exact tRWR rejected");

    // Linear transfer wraps from the final 16-bit word to word zero.
    #6;
    write_word('hffffff, 8'h12, 8'h34, 0, 7);
    #6;
    write_word(0, 8'h56, 8'h78, 0, 7);
    #6;
    cs_n = 0;
    #4;
    ca(make_ca(1, 0, 1, 'hffffff));
    idle_ck(7);
    tick(0, 0, 0, 0, 0, 0, hi, lo);
    if ({hi, lo} !== 16'h1234) $fatal(1, "end-of-array first word");
    tick(0, 0, 0, 0, 0, 0, hi, lo);
    cs_n = 1;
    if ({hi, lo} !== 16'h5678 || dut.violations != v)
      $fatal(1, "end-of-array linear wrap");

    // Maximum CS# low is an absolute duration, including stalled clocks.
    #6;
    cs_n = 0;
    #4;
    ca(make_ca(1, 0, 1, 'h10));
    idle_ck(7);
    tick(0, 0, 0, 0, 0, 0, hi, lo);
    v = dut.violations;
    #4000;
    cs_n = 1;
    #0.001;
    if (dut.violations != v + 1) $fatal(1, "tCSM overrun not detected once");

    // RESET# low/high minima and CS# setup are independent AC constraints.
    #6 reset_n = 0;
    v = dut.violations;
    #199 reset_n = 1;
    #0.001;
    if (dut.violations != v + 1) $fatal(1, "early tRP not detected");
    v = dut.violations;
    #199 cs_n = 0;
    #0.001;
    if (dut.violations != v + 1) $fatal(1, "early tRH not detected");
    #4;
    ca(make_ca(1, 0, 1, 'h10));
    idle_ck(14);
    tick(0, 0, 0, 0, 0, 0, hi, lo);
    cs_n = 1;
    #6;
    v = dut.violations;
    cs_n = 0;
    ca(make_ca(1, 0, 1, 'h10)); // first CK edge only 2.5 ns after CS#
    idle_ck(14);
    tick(0, 0, 0, 0, 0, 0, hi, lo);
    cs_n = 1;
    if (dut.violations != v + 1) $fatal(1, "early tCSS not detected");

    $display("PASS hyperram pin positive=%0d expected_negative=%0d collisions=%0d",
      dut.transactions, dut.violations, dut.collisions);
    $finish;
  end
endmodule
