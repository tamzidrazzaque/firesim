`timescale 1ns/1ps
`include "axi/typedef.svh"

module tb_eth_interface_data;
  typedef logic [47:0] addr_t;
  typedef logic [63:0] data_t;
  typedef logic [5:0] id_t;
  typedef logic [7:0] strb_t;
  typedef logic user_t;
  `AXI_TYPEDEF_AW_CHAN_T(aw_t, addr_t, id_t, user_t)
  `AXI_TYPEDEF_W_CHAN_T(w_t, data_t, strb_t, user_t)
  `AXI_TYPEDEF_B_CHAN_T(b_t, id_t, user_t)
  `AXI_TYPEDEF_AR_CHAN_T(ar_t, addr_t, id_t, user_t)
  `AXI_TYPEDEF_R_CHAN_T(r_t, data_t, id_t, user_t)
  `AXI_TYPEDEF_REQ_T(req_t, aw_t, w_t, ar_t)
  `AXI_TYPEDEF_RESP_T(rsp_t, b_t, r_t)

  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0;
  req_t req;
  rsp_t rsp;
  rpc_ctrl_pkg::phy_req_t phy_req;
  rpc_ctrl_pkg::phy_rsp_t phy_rsp;
  rpc_ctrl_pkg::axi_cmd_req_t cmd_req;
  rpc_ctrl_pkg::axi_cmd_rsp_t cmd_rsp;
  logic [63:0] write_mask;
  logic phy_cmd_valid;
  logic [31:0] phy_cmd;
  logic init_done, direct_ready, ref_ready, zqc_ready;
  rpc_config_path_pkg::dram_init_cfg_reg_t init_cfg;

  rpc_interface #(
    .axi_req_t(req_t), .axi_rsp_t(rsp_t),
    .phy_req_t(rpc_ctrl_pkg::phy_req_t),
    .phy_rsp_t(rpc_ctrl_pkg::phy_rsp_t),
    .cmd_req_t(rpc_ctrl_pkg::axi_cmd_req_t),
    .cmd_rsp_t(rpc_ctrl_pkg::axi_cmd_rsp_t)
  ) dut (
    .clk_i(clk), .rst_ni(rst_n), .axi_req_i(req), .axi_resp_o(rsp),
    .phy_req_o(phy_req), .phy_rsp_i(phy_rsp),
    .cmd_req_o(cmd_req), .cmd_rsp_i(cmd_rsp), .write_mask_o(write_mask)
  );

  rpc_cmd_fsm cmd_fsm (
    .clk_i(clk), .rst_ni(rst_n),
    .data_path_valid_i(cmd_req.cmd_valid),
    .data_path_ready_o(cmd_rsp.cmd_ready),
    .data_path_addr_i(cmd_req.addr),
    .data_path_len_i(cmd_req.len),
    .data_path_is_write_i(cmd_req.is_write),
    .direct_cmd_valid_i(1'b0), .direct_cmd_ready_o(direct_ready), .direct_cmd_i('0),
    .launch_init_i(1'b0), .dram_init_config_i(init_cfg),
    .rpc_init_completed_o(init_done),
    .ref_valid_i(1'b0), .ref_ready_o(ref_ready), .ref_cmd_i('0),
    .zqc_valid_i(1'b0), .zqc_ready_o(zqc_ready), .zqc_cmd_i('0),
    .phy_ready_i(1'b1), .phy_valid_o(phy_cmd_valid), .phy_cmd_o(phy_cmd)
  );

  logic [255:0] device_word [0:3];
  logic [1:0] write_bank, read_bank;
  int write_cmds = 0;
  int read_cmds = 0;
  int write_words = 0;
  int read_words = 0;
  int read_delay = -1;
  logic write_pending = 0;
  int acts = 0;
  int pres = 0;
  int rd_cas = 0;
  int wr_cas = 0;
  logic [1:0] current_phy_bank;
  always @(posedge clk) if (rst_n) begin
    if (dut.up_req_o.aw_valid && dut.up_resp_i.aw_ready)
      $display("UP_AW addr=%h len=%0d burst=%0d", dut.up_req_o.aw.addr,
        dut.up_req_o.aw.len, dut.up_req_o.aw.burst);
    if (rsp.b_valid)
      $display("B_MON id=%h resp=%h err=%b", rsp.b.id, rsp.b.resp,
        dut.i_axi_dw_upsizer.mst_req_aw_err);
  end

  // This is a transaction-side RPC device: it stores the 256-bit PHY word.
  // The ETH interface and its production queues/upsizer are unmodified.
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      phy_rsp <= '0;
      read_delay <= -1;
      write_pending <= 0;
    end else begin
      phy_rsp.w_data_ready <= write_pending;
      if (cmd_req.cmd_valid && cmd_rsp.cmd_ready) begin
        if (cmd_req.is_write) begin
          write_cmds <= write_cmds + 1;
          write_bank <= cmd_req.addr[19:18];
          $display("ETH_CMD WRITE addr=%h len=%0d mask=%h", cmd_req.addr, cmd_req.len, write_mask);
        end else begin
          read_cmds <= read_cmds + 1;
          read_bank <= cmd_req.addr[19:18];
          $display("ETH_CMD READ addr=%h len=%0d", cmd_req.addr, cmd_req.len);
        end
      end
      if (phy_cmd_valid) begin
        $display("ETH_PHY_CMD %h", phy_cmd);
        case (phy_cmd[18:16])
          3'b101: begin
            if (phy_cmd[20:19] != 2'(acts < 8 ? acts / 2 : acts - 8))
              $fatal(1, "ACT bank mismatch: got %0d at ACT %0d", phy_cmd[20:19], acts);
            current_phy_bank <= phy_cmd[20:19];
            acts <= acts + 1;
          end
          3'b100: begin
            if (phy_cmd[25:22] != (4'b0001 << current_phy_bank))
              $fatal(1, "PRE bank mismatch: got %h expected bank %0d", phy_cmd[25:22], current_phy_bank);
            pres <= pres + 1;
          end
          3'b001: if (!phy_cmd[0]) begin
            if (phy_cmd[20:19] != current_phy_bank)
              $fatal(1, "WR bank differs from ACT bank");
            wr_cas <= wr_cas + 1;
            write_pending <= 1;
          end
          3'b000: if (!phy_cmd[0]) begin
            if (phy_cmd[20:19] != current_phy_bank)
              $fatal(1, "RD bank differs from ACT bank");
            rd_cas <= rd_cas + 1;
            read_delay <= 4;
          end
          default: ;
        endcase
      end
      if (phy_req.w_data_valid && phy_rsp.w_data_ready) begin
        if (write_mask[63:32] != write_mask[31:0])
          $fatal(1, "Single-word first/last masks differ: %h", write_mask);
        for (int byte_idx = 0; byte_idx < 32; byte_idx++) begin
          if (!write_mask[byte_idx])
            device_word[write_bank][byte_idx*8 +: 8] <= phy_req.w_data[byte_idx*8 +: 8];
        end
        write_words <= write_words + 1;
        write_pending <= 0;
        $display("ETH_DATA WRITE word=%h mask=%h", phy_req.w_data, write_mask);
      end
      if (read_delay > 0) read_delay <= read_delay - 1;
      if (read_delay == 0) begin
        phy_rsp.r_data <= device_word[read_bank];
        phy_rsp.r_data_last <= 1;
        phy_rsp.r_data_valid <= 1;
        read_delay <= -1;
      end
      if (phy_rsp.r_data_valid && phy_req.r_data_ready) begin
        phy_rsp.r_data_valid <= 0;
        read_words <= read_words + 1;
        $display("ETH_DATA READ word=%h", phy_rsp.r_data);
      end
    end
  end

  task automatic send_aw(input int bank);
    @(negedge clk);
    req.aw = '0;
    req.aw.addr = 48'h100 + (bank * 48'h800000);
    req.aw.id = 6'h15;
    req.aw.len = 0;
    req.aw.size = 3;
    req.aw.burst = axi_pkg::BURST_INCR;
    req.aw_valid = 1;
    do @(posedge clk); while (!rsp.aw_ready);
    @(negedge clk); req.aw_valid = 0;
  endtask

  task automatic send_w(input logic [63:0] data, input logic [7:0] strobe);
    @(negedge clk);
    req.w = '0;
    req.w.data = data;
    req.w.strb = strobe;
    req.w.last = 1;
    req.w_valid = 1;
    do @(posedge clk); while (!rsp.w_ready);
    @(negedge clk); req.w_valid = 0;
  endtask

  task automatic send_ar(input int bank);
    @(negedge clk);
    req.ar = '0;
    req.ar.addr = 48'h100 + (bank * 48'h800000);
    req.ar.id = 6'h2a;
    req.ar.len = 0;
    req.ar.size = 3;
    req.ar.burst = axi_pkg::BURST_INCR;
    req.ar_valid = 1;
    do @(posedge clk); while (!rsp.ar_ready);
    @(negedge clk); req.ar_valid = 0;
  endtask

  initial begin
    req = '0;
    init_cfg = '0;
    req.b_ready = 0;
    req.r_ready = 1;
    repeat (5) @(negedge clk);
    rst_n = 1;
    for (int bank = 0; bank < 4; bank++) begin
      send_aw(bank);
      send_w(64'h0102_0304_0506_0708 + bank, 8'hff);
      do @(posedge clk); while (!rsp.b_valid);
      $display("ETH_AXI WRITE bank=%0d id=%h resp=%h", bank, rsp.b.id, rsp.b.resp);
      if (rsp.b.resp != axi_pkg::RESP_OKAY || rsp.b.id != 6'h15)
        $fatal(1, "AXI write response incorrect bank %0d", bank);
      @(negedge clk); req.b_ready = 1;
      @(negedge clk); req.b_ready = 0;
      send_aw(bank);
      send_w(64'hf1e2_d3c4_b5a6_9788 + bank, 8'h53);
      do @(posedge clk); while (!rsp.b_valid);
      if (rsp.b.resp != axi_pkg::RESP_OKAY || rsp.b.id != 6'h15)
        $fatal(1, "AXI partial write response incorrect bank %0d", bank);
      @(negedge clk); req.b_ready = 1;
      @(negedge clk); req.b_ready = 0;
    end
    for (int bank = 0; bank < 4; bank++) begin
      send_ar(bank);
      do @(posedge clk); while (!rsp.r_valid);
      for (int byte_idx = 0; byte_idx < 8; byte_idx++) begin
        logic [63:0] first_data, partial_data;
        first_data = 64'h0102_0304_0506_0708 + bank;
        partial_data = 64'hf1e2_d3c4_b5a6_9788 + bank;
        if (rsp.r.data[byte_idx*8 +: 8] !=
            (((8'h53 >> byte_idx) & 1) ? partial_data[byte_idx*8 +: 8] : first_data[byte_idx*8 +: 8]))
          $fatal(1, "Masked byte mismatch in bank %0d byte %0d", bank, byte_idx);
      end
      if (rsp.r.id != 6'h2a || rsp.r.resp != axi_pkg::RESP_OKAY || !rsp.r.last)
        $fatal(1, "AXI read bank %0d incorrect: %h last=%b", bank, rsp.r.data, rsp.r.last);
      $display("ETH_AXI READ bank=%0d data=%h", bank, rsp.r.data);
    end
    if (write_cmds != 8 || read_cmds != 4 || write_words != 8 || read_words != 4 ||
        acts != 12 || pres != 12 || wr_cas != 8 || rd_cas != 4)
      $fatal(1, "Wrong transaction counts: cmds=%0d/%0d words=%0d/%0d",
        write_cmds, read_cmds, write_words, read_words);
    $display("PASS ETH AXI interface and command FSM data path");
    $finish;
  end

  initial begin
    #100000;
    $fatal(1, "Timeout in ETH interface data path");
  end
endmodule
