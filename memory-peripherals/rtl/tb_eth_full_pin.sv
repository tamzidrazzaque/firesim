`timescale 1ns/1ps

// First bring-up of the complete ETH top. A pin-side model will be attached
// after verifying the actual command and strobe timing from this monitor.
module tb_eth_full_pin;
  logic clk_i = 0;
  always #2.5 clk_i = ~clk_i;
  logic rst_ni = 0;

  logic [5:0] axi_aw_id_i = 0, axi_b_id_o, axi_ar_id_i = 0, axi_r_id_o;
  logic [47:0] axi_aw_addr_i = 0, axi_ar_addr_i = 0;
  logic [7:0] axi_aw_len_i = 0, axi_ar_len_i = 0;
  logic [2:0] axi_aw_size_i = 3, axi_ar_size_i = 3;
  logic [1:0] axi_aw_burst_i = 1, axi_ar_burst_i = 1;
  logic axi_aw_lock_i = 0, axi_ar_lock_i = 0;
  logic [3:0] axi_aw_cache_i = 4'b0010, axi_ar_cache_i = 4'b0010;
  logic [2:0] axi_aw_prot_i = 0, axi_ar_prot_i = 0;
  logic [3:0] axi_aw_qos_i = 0, axi_ar_qos_i = 0;
  logic [3:0] axi_aw_region_i = 0, axi_ar_region_i = 0;
  logic [5:0] axi_aw_atop_i = 0;
  logic [0:0] axi_aw_user_i = 0, axi_w_user_i = 0, axi_ar_user_i = 0;
  logic [0:0] axi_b_user_o, axi_r_user_o;
  logic axi_aw_valid_i = 0, axi_aw_ready_o;
  logic [63:0] axi_w_data_i = 0, axi_r_data_o;
  logic [7:0] axi_w_strb_i = 8'hff;
  logic axi_w_last_i = 1, axi_w_valid_i = 0, axi_w_ready_o;
  logic [1:0] axi_b_resp_o, axi_r_resp_o;
  logic axi_b_valid_o, axi_b_ready_i = 1;
  logic axi_ar_valid_i = 0, axi_ar_ready_o;
  logic axi_r_last_o, axi_r_valid_o, axi_r_ready_i = 1;
  logic [47:0] reg_addr_i = 0;
  logic reg_write_i = 0;
  logic [31:0] reg_wdata_i = 0, reg_rdata_o;
  logic [3:0] reg_wstrb_i = 4'hf;
  logic reg_valid_i = 0, reg_error_o, reg_ready_o;
  logic rpc_clk_o, rpc_clk_no, rpc_cs_no, rpc_stb_o;
  logic phy_dqs_o, phy_dqs_n_o, phy_dqs_i, phy_dqs_n_i;
  logic phy_dqs_pair_oe_o, phy_dqs_pair_ie_o, phy_dqs_pair_pd_en_o;
  logic [15:0] phy_db_o, phy_db_i;
  logic phy_db_oe_o, phy_db_ie_o, phy_db_pd_en_o;

  rpc_synth_wrap dut (.*);
  rpc_pin_memory device (
    .clk_i(rpc_clk_o), .rst_ni(rst_ni), .cs_ni(rpc_cs_no),
    .stb_i(rpc_stb_o), .db_i(phy_db_o), .db_oe_i(phy_db_oe_o),
    .dqs_oe_i(phy_dqs_pair_oe_o), .db_o(phy_db_i),
    .dqs_o(phy_dqs_i), .dqs_no(phy_dqs_n_i)
  );

  int cycle = 0;
  always @(posedge clk_i) if (rst_ni) begin
    cycle <= cycle + 1;
    if (cycle >= 41580 && cycle < 41720) begin
      $display("PIN c=%0d cs=%b stb=%b db=%h db_oe=%b dqs=%b dqs_oe=%b cmd=%h tstate=%0d",
        cycle, rpc_cs_no, rpc_stb_o, phy_db_o, phy_db_oe_o, phy_dqs_o, phy_dqs_pair_oe_o,
        dut.i_rpc.i_rpc_controller.i_rpc_phy_controller.arb_o_phy_i_cmd,
        dut.i_rpc.i_rpc_controller.i_rpc_phy_controller.i_rpc_phy.i_rpc_timing_fsm.state_q);
    end
    if (axi_b_valid_o) $display("AXI_B c=%0d id=%0d resp=%0d",cycle,axi_b_id_o,axi_b_resp_o);
  end
  always @(negedge rpc_clk_o) if (rst_ni && cycle >= 41580 && cycle < 41720 && phy_db_oe_o)
    $display("PIN_FALL c=%0d db=%h stb=%b", cycle, phy_db_o, rpc_stb_o);

  task automatic write_reg(input logic [47:0] addr, input logic [31:0] value);
    @(negedge clk_i);
    reg_addr_i = addr;
    reg_wdata_i = value;
    reg_write_i = 1;
    reg_valid_i = 1;
    do @(posedge clk_i); while (!reg_ready_o);
    @(negedge clk_i);
    reg_valid_i = 0;
    reg_write_i = 0;
  endtask

  initial begin
    repeat (6) @(negedge clk_i);
    rst_ni = 1;
    // Register offsets are from rpc_config_path_pkg. 200 MHz timing values
    // are rounded upward from Etron Rev. 1.4, Tables 11-3 and Fig. 4-1.
    for (int i = 0; i < 21; i++) write_reg(48'(36 + 4*i), 2);
    write_reg(36, 40000); // clock stable 200 us
    write_reg(40, 1000);  // reset complete 5 us
    write_reg(44, 16);    // two serial reset packets
    write_reg(48, 2);     // CS setup/hold
    write_reg(56, 3);     // precharge tRP
    write_reg(60, 12);    // tMOD
    write_reg(64, 3);     // tRCD
    write_reg(68, 3);     // CL=3
    write_reg(76, 11);    // write end to STB
    write_reg(84, 9);     // read end to STB
    write_reg(104, 400);  // ZQINIT 2 us
    write_reg(24, 8);     // quarter-cycle output clock shift
    write_reg(28, 8);     // DQS input shift
    write_reg(32, 8);
    write_reg(0, 32'h04000000); // CL=8, nonzero Zout; launch initialization
    wait (dut.i_rpc.i_rpc_controller.mgnmt_i_ctrl_o_init_flag);
    $display("INIT_DONE c=%0d", cycle);
    repeat (10) @(negedge clk_i);
    axi_aw_addr_i = 48'h100;
    axi_aw_id_i = 6'h15;
    axi_aw_valid_i = 1;
    do @(posedge clk_i); while (!axi_aw_ready_o);
    @(negedge clk_i); axi_aw_valid_i = 0;
    axi_w_data_i = 64'h1122334455667788;
    axi_w_valid_i = 1;
    do @(posedge clk_i); while (!axi_w_ready_o);
    @(negedge clk_i); axi_w_valid_i = 0;
    repeat (100) @(negedge clk_i);
    axi_ar_addr_i = 48'h100;
    axi_ar_id_i = 6'h2a;
    axi_ar_valid_i = 1;
    do @(posedge clk_i); while (!axi_ar_ready_o);
    @(negedge clk_i); axi_ar_valid_i = 0;
    do @(posedge clk_i); while (!axi_r_valid_o);
    if (axi_r_data_o != 64'h1122334455667788 || axi_r_id_o != 6'h2a ||
        axi_r_resp_o != 0 || !axi_r_last_o)
      $fatal(1,"Full ETH pin readback mismatch: %h id=%0d",axi_r_data_o,axi_r_id_o);
    $display("PASS full ETH pin 8-byte write/read data=%h",axi_r_data_o);
    @(negedge clk_i);
    axi_aw_addr_i = 48'h100;
    axi_aw_len_i = 0;
    axi_aw_valid_i = 1;
    do @(posedge clk_i); while (!axi_aw_ready_o);
    @(negedge clk_i); axi_aw_valid_i = 0;
    axi_w_data_i = 64'haabbccddeeff0011;
    axi_w_strb_i = 8'h0f;
    axi_w_valid_i = 1;
    do @(posedge clk_i); while (!axi_w_ready_o);
    @(negedge clk_i); axi_w_valid_i = 0;
    repeat (100) @(negedge clk_i);
    axi_ar_addr_i = 48'h100;
    axi_ar_len_i = 0;
    axi_ar_valid_i = 1;
    do @(posedge clk_i); while (!axi_ar_ready_o);
    @(negedge clk_i); axi_ar_valid_i = 0;
    do @(posedge clk_i); while (!axi_r_valid_o);
    if (axi_r_data_o != 64'h11223344eeff0011)
      $fatal(1,"Full ETH partial write failed: %h",axi_r_data_o);
    $display("PASS full ETH pin partial-byte write data=%h",axi_r_data_o);
    @(negedge clk_i);
    axi_w_strb_i = 8'hff;
    axi_aw_addr_i = 48'h200;
    axi_aw_len_i = 7;
    axi_aw_valid_i = 1;
    do @(posedge clk_i); while (!axi_aw_ready_o);
    @(negedge clk_i); axi_aw_valid_i = 0;
    for (int beat = 0; beat < 8; beat++) begin
      axi_w_data_i = 64'hcafe000000000000 | 64'(beat);
      axi_w_last_i = beat == 7;
      axi_w_valid_i = 1;
      do @(posedge clk_i); while (!axi_w_ready_o);
      @(negedge clk_i);
    end
    axi_w_valid_i = 0;
    axi_w_last_i = 1;
    repeat (100) @(negedge clk_i);
    axi_ar_addr_i = 48'h200;
    axi_ar_len_i = 7;
    axi_ar_valid_i = 1;
    do @(posedge clk_i); while (!axi_ar_ready_o);
    @(negedge clk_i); axi_ar_valid_i = 0;
    for (int beat = 0; beat < 8; beat++) begin
      do @(posedge clk_i); while (!axi_r_valid_o);
      if (axi_r_data_o != (64'hcafe000000000000 | 64'(beat)) ||
          axi_r_last_o != (beat == 7))
        $fatal(1,"Full ETH burst beat %0d mismatch: %h last=%b",beat,axi_r_data_o,axi_r_last_o);
    end
    $display("PASS full ETH pin 64-byte burst");
    $finish;
  end
  initial begin
    #1_000_000;
    $fatal(1,"Full ETH pin test timeout");
  end
endmodule
