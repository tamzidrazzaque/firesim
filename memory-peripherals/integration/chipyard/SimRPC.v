`timescale 1ns/1ps
module SimRPC #(
  parameter ADDR_BITS=32, DATA_BITS=64, ID_BITS=5,
  parameter [63:0] MEM_BASE=64'h80000000
)(

  input clock, input reset,
  input axi_aw_valid, output axi_aw_ready,
  input [ADDR_BITS-1:0] axi_aw_bits_addr,
  input [7:0] axi_aw_bits_len,
  input [2:0] axi_aw_bits_size,
  input [1:0] axi_aw_bits_burst,
  input axi_aw_bits_lock,
  input [3:0] axi_aw_bits_cache,
  input [2:0] axi_aw_bits_prot,
  input [3:0] axi_aw_bits_qos,
  input [ID_BITS-1:0] axi_aw_bits_id,
  input axi_w_valid, output axi_w_ready,
  input [DATA_BITS-1:0] axi_w_bits_data,
  input [DATA_BITS/8-1:0] axi_w_bits_strb,
  input axi_w_bits_last,
  output axi_b_valid, input axi_b_ready,
  output [1:0] axi_b_bits_resp,
  output [ID_BITS-1:0] axi_b_bits_id,
  input axi_ar_valid, output axi_ar_ready,
  input [ADDR_BITS-1:0] axi_ar_bits_addr,
  input [7:0] axi_ar_bits_len,
  input [2:0] axi_ar_bits_size,
  input [1:0] axi_ar_bits_burst,
  input axi_ar_bits_lock,
  input [3:0] axi_ar_bits_cache,
  input [2:0] axi_ar_bits_prot,
  input [3:0] axi_ar_bits_qos,
  input [ID_BITS-1:0] axi_ar_bits_id,
  output axi_r_valid, input axi_r_ready,
  output [1:0] axi_r_bits_resp,
  output [DATA_BITS-1:0] axi_r_bits_data,
  output axi_r_bits_last,
  output [ID_BITS-1:0] axi_r_bits_id
);
  logic rst_ni;
  assign rst_ni = !reset;
  logic [47:0] reg_addr_i;
  logic [31:0] reg_wdata_i;
  logic reg_valid_i, reg_ready_o, reg_error_o;
  logic [31:0] reg_rdata_o;
  logic [7:0] cfg_step;
  logic cfg_done;
  logic [31:0] cfg_value;
  always_comb begin
    reg_addr_i = 48'(36 + 4*cfg_step);
    cfg_value = 2;
    case (cfg_step)
      0: cfg_value = 40000; // stable clock >= 200us at 200 MHz
      1: cfg_value = 1000;  // reset >= 5us
      2: cfg_value = 16;
      3: cfg_value = 2;
      5: cfg_value = 3;     // tRP
      6: cfg_value = 12;    // tMOD
      7: cfg_value = 3;     // tRCD
      8: cfg_value = 3;
      10: cfg_value = 11;   // write to command gap
      12: cfg_value = 9;    // read to command gap
      13: cfg_value = 327680; // REF, four banks: 4096 * 20 * 4 CK
      14: cfg_value = 245760; // three banks
      15: cfg_value = 163840; // two banks
      16: cfg_value = 81920;  // one bank
      17: cfg_value = 400;  // ZQINIT >= 2us
      21,22,23: cfg_value = 8; // clock and DQS delays
      24: cfg_value = 32'h04000000; // CL8 mode and init start
      default: ;
    endcase
    if (cfg_step == 21) reg_addr_i = 24;
    if (cfg_step == 22) reg_addr_i = 28;
    if (cfg_step == 23) reg_addr_i = 32;
    if (cfg_step == 24) reg_addr_i = 0;
    reg_valid_i = (cfg_step <= 24);
  end
  always @(posedge clock) begin
    if (reset) begin cfg_step <= 0; cfg_done <= 0; end
    else if (reg_valid_i && reg_ready_o) begin
      if (reg_error_o) $fatal(1,"ETH RegBus configuration error at step %0d",cfg_step);
      cfg_step <= cfg_step + 1;
    end else if (cfg_step == 25 &&
      controller.i_rpc.i_rpc_controller.mgnmt_i_ctrl_o_init_flag) cfg_done <= 1;
  end
  logic rpc_clk_o, rpc_clk_no, rpc_cs_no, rpc_stb_o;
  logic phy_dqs_o, phy_dqs_n_o, phy_dqs_i, phy_dqs_n_i;
  logic phy_dqs_pair_oe_o, phy_dqs_pair_ie_o, phy_dqs_pair_pd_en_o;
  logic [15:0] phy_db_o, phy_db_i;
  logic phy_db_oe_o, phy_db_ie_o, phy_db_pd_en_o;
  logic aw_ready, w_ready, ar_ready;
  assign axi_aw_ready = cfg_done && aw_ready;
  assign axi_w_ready = cfg_done && w_ready;
  assign axi_ar_ready = cfg_done && ar_ready;
  rpc_synth_wrap controller (
    .clk_i(clock), .rst_ni(rst_ni),
    .axi_aw_id_i(6'(axi_aw_bits_id)),
    .axi_aw_addr_i(48'(axi_aw_bits_addr - ADDR_BITS'(MEM_BASE))),
    .axi_aw_len_i(axi_aw_bits_len), .axi_aw_size_i(axi_aw_bits_size),
    .axi_aw_burst_i(axi_aw_bits_burst), .axi_aw_lock_i(axi_aw_bits_lock),
    // ETH's 64-to-256-bit upsizer requires AXI CACHE[1] (modifiable).
    // Chipyard's memory port leaves it low even for normal DRAM accesses.
    .axi_aw_cache_i(axi_aw_bits_cache | 4'b0010), .axi_aw_prot_i(axi_aw_bits_prot),
    .axi_aw_qos_i(axi_aw_bits_qos), .axi_aw_region_i(4'b0),
    .axi_aw_atop_i(6'b0), .axi_aw_user_i(1'b0),
    .axi_aw_valid_i(cfg_done && axi_aw_valid), .axi_aw_ready_o(aw_ready),
    .axi_w_data_i(axi_w_bits_data), .axi_w_strb_i(axi_w_bits_strb),
    .axi_w_last_i(axi_w_bits_last), .axi_w_user_i(1'b0),
    .axi_w_valid_i(cfg_done && axi_w_valid), .axi_w_ready_o(w_ready),
    .axi_b_id_o(axi_b_bits_id), .axi_b_resp_o(axi_b_bits_resp),
    .axi_b_user_o(), .axi_b_valid_o(axi_b_valid), .axi_b_ready_i(axi_b_ready),
    .axi_ar_id_i(6'(axi_ar_bits_id)),
    .axi_ar_addr_i(48'(axi_ar_bits_addr - ADDR_BITS'(MEM_BASE))),
    .axi_ar_len_i(axi_ar_bits_len), .axi_ar_size_i(axi_ar_bits_size),
    .axi_ar_burst_i(axi_ar_bits_burst), .axi_ar_lock_i(axi_ar_bits_lock),
    .axi_ar_cache_i(axi_ar_bits_cache | 4'b0010), .axi_ar_prot_i(axi_ar_bits_prot),
    .axi_ar_qos_i(axi_ar_bits_qos), .axi_ar_region_i(4'b0),
    .axi_ar_user_i(1'b0), .axi_ar_valid_i(cfg_done && axi_ar_valid),
    .axi_ar_ready_o(ar_ready), .axi_r_id_o(axi_r_bits_id),
    .axi_r_data_o(axi_r_bits_data), .axi_r_resp_o(axi_r_bits_resp),
    .axi_r_last_o(axi_r_bits_last), .axi_r_user_o(),
    .axi_r_valid_o(axi_r_valid), .axi_r_ready_i(axi_r_ready),
    .reg_addr_i(reg_addr_i), .reg_write_i(1'b1), .reg_wdata_i(cfg_value),
    .reg_wstrb_i(4'hf), .reg_valid_i(reg_valid_i),
    .reg_error_o(reg_error_o), .reg_rdata_o(reg_rdata_o), .reg_ready_o(reg_ready_o),
    .rpc_clk_o(rpc_clk_o), .rpc_clk_no(rpc_clk_no),
    .rpc_cs_no(rpc_cs_no), .rpc_stb_o(rpc_stb_o),
    .phy_dqs_o(phy_dqs_o), .phy_dqs_n_o(phy_dqs_n_o),
    .phy_dqs_i(phy_dqs_i), .phy_dqs_n_i(phy_dqs_n_i),
    .phy_dqs_pair_oe_o(phy_dqs_pair_oe_o),
    .phy_dqs_pair_ie_o(phy_dqs_pair_ie_o),
    .phy_dqs_pair_pd_en_o(phy_dqs_pair_pd_en_o),
    .phy_db_o(phy_db_o), .phy_db_i(phy_db_i),
    .phy_db_oe_o(phy_db_oe_o), .phy_db_ie_o(phy_db_ie_o),
    .phy_db_pd_en_o(phy_db_pd_en_o)
  );
  rpc_pin_memory #(.FATAL_ON_REFRESH_BUSY(1)) device (
    .clk_i(rpc_clk_o), .rst_ni(rst_ni), .cs_ni(rpc_cs_no),
    .stb_i(rpc_stb_o), .db_i(phy_db_o), .db_oe_i(phy_db_oe_o),
    .dqs_oe_i(phy_dqs_pair_oe_o), .db_o(phy_db_i),
    .dqs_o(phy_dqs_i), .dqs_no(phy_dqs_n_i)
  );
  // Observes the same pins. It does not drive them and cannot delay a command.
  rpc_timing_observe #(.REFRESH_ROW_STEP(1), .FATAL_ON_VIOLATION(1)) timing_observe (
    .clk_i(rpc_clk_o), .rst_ni(rst_ni), .cs_ni(rpc_cs_no),
    .stb_i(rpc_stb_o), .db_i(phy_db_o), .db_oe_i(phy_db_oe_o)
  );
  initial begin
    if (DATA_BITS != 64 || ID_BITS > 6) $fatal(1,"Unsupported AXI geometry");
  end
endmodule
