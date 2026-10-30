// Command-level test of the ETH rpc_cmd_fsm (not the PHY and not rpc.sv).
// phy_ready is tied high, so each command is visible for one cycle:
// ACT, then RD or WR, then PRE. That is the closed-page sequence in the FSM.
// DRAM tRCD is enforced by rpc_timing_fsm, which this bench does not instantiate.
`timescale 1ns/1ps

module tb_rpc_cmd_fsm;
  logic clk = 0;
  logic rst_ni = 0;
  always #5 clk = ~clk;

  logic        data_path_valid, data_path_ready, data_path_is_write;
  logic [19:0] data_path_addr;
  logic [5:0]  data_path_len;
  logic        direct_cmd_valid, direct_cmd_ready;
  logic [18:0] direct_cmd;
  logic        launch_init, rpc_init_completed;
  logic        ref_valid, ref_ready, zqc_valid, zqc_ready;
  logic [18:0] ref_cmd, zqc_cmd;
  logic        phy_ready, phy_valid;
  logic [31:0] phy_cmd;
  rpc_config_path_pkg::dram_init_cfg_reg_t init_cfg;

  rpc_cmd_fsm dut (
    .clk_i(clk),
    .rst_ni(rst_ni),
    .data_path_valid_i(data_path_valid),
    .data_path_ready_o(data_path_ready),
    .data_path_addr_i(data_path_addr),
    .data_path_len_i(data_path_len),
    .data_path_is_write_i(data_path_is_write),
    .direct_cmd_valid_i(direct_cmd_valid),
    .direct_cmd_ready_o(direct_cmd_ready),
    .direct_cmd_i(direct_cmd),
    .launch_init_i(launch_init),
    .dram_init_config_i(init_cfg),
    .rpc_init_completed_o(rpc_init_completed),
    .ref_valid_i(ref_valid),
    .ref_ready_o(ref_ready),
    .ref_cmd_i(ref_cmd),
    .zqc_valid_i(zqc_valid),
    .zqc_ready_o(zqc_ready),
    .zqc_cmd_i(zqc_cmd),
    .phy_ready_i(phy_ready),
    .phy_valid_o(phy_valid),
    .phy_cmd_o(phy_cmd)
  );

  int cycle;
  int errors;
  int seen_act, seen_rd, seen_wr, seen_pre;
  logic [2:0] opc;
  logic [2:0] seq [0:31];
  int nseq;

  task automatic tick;
    begin
      @(posedge clk);
      #1;
      cycle = cycle + 1;
      if (phy_valid) begin
        opc = phy_cmd[18:16];
        $display("ETHCMD,%0d,%h,%0d", cycle, phy_cmd, opc);
        if (opc == 3'b101) seen_act = seen_act + 1;
        if (opc == 3'b000 && phy_cmd[0] == 1'b0) seen_rd = seen_rd + 1;
        if (opc == 3'b001 && phy_cmd[0] == 1'b0) seen_wr = seen_wr + 1;
        if (opc == 3'b100) seen_pre = seen_pre + 1;
        if (nseq < 32) begin
          seq[nseq] = opc;
          nseq = nseq + 1;
        end
      end
    end
  endtask

  initial begin
    errors = 0;
    cycle = 0;
    seen_act = 0;
    seen_rd = 0;
    seen_wr = 0;
    seen_pre = 0;
    nseq = 0;
    data_path_valid = 0;
    data_path_addr = 0;
    data_path_len = 0;
    data_path_is_write = 0;
    direct_cmd_valid = 0;
    direct_cmd = 0;
    launch_init = 0;
    init_cfg = '0;
    ref_valid = 0;
    ref_cmd = 0;
    zqc_valid = 0;
    zqc_cmd = 0;
    phy_ready = 1;
    repeat (4) @(posedge clk);
    rst_ni = 1;
    repeat (2) tick();

    // Read, bank 1, row 0x15, column group 0, one word (BC=0).
    data_path_addr = {2'b01, 12'h015, 6'h00};
    data_path_len = 6'd0;
    data_path_is_write = 0;
    data_path_valid = 1;
    tick();
    while (!data_path_ready && cycle < 20) tick();
    data_path_valid = 0;
    repeat (8) tick();

    // Write, bank 2, row 3.
    data_path_addr = {2'b10, 12'h003, 6'h04};
    data_path_len = 6'd1; // two 32-byte words
    data_path_is_write = 1;
    data_path_valid = 1;
    tick();
    while (!data_path_ready && cycle < 40) tick();
    data_path_valid = 0;
    repeat (8) tick();

    begin
      int i;
      int saw_read_triple, saw_write_triple;
      saw_read_triple = 0;
      saw_write_triple = 0;
      for (i = 0; i + 2 < nseq; i = i + 1) begin
        // 5 = ACT, 0 = RD, 1 = WR, 4 = PRE. Closed-page order from the FSM.
        if (seq[i] == 3'd5 && seq[i+1] == 3'd0 && seq[i+2] == 3'd4)
          saw_read_triple = 1;
        if (seq[i] == 3'd5 && seq[i+1] == 3'd1 && seq[i+2] == 3'd4)
          saw_write_triple = 1;
      end
      if (!saw_read_triple || !saw_write_triple) begin
        $display("FAIL read_triple=%0d write_triple=%0d", saw_read_triple, saw_write_triple);
        errors = errors + 1;
      end else $display("PASS closed-page ACT/CAS/PRE for read and write");
    end
    // tRCD is not inserted here. rpc_timing_fsm owns that delay.

    if (errors == 0) begin
      $display("ALL PASS");
      $finish;
    end else begin
      $fatal(1);
    end
  end
endmodule
