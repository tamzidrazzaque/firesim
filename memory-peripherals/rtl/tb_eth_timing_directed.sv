`timescale 1ns/1ps

// Directed ETH controller tests with the online timing observer attached.
// The observer does not sit on phy_ready, so an illegal command is still issued.
module tb_eth_timing_directed;
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
  logic axi_b_valid_o, axi_b_ready_i = 0;
  logic axi_ar_valid_i = 0, axi_ar_ready_o;
  logic axi_r_last_o, axi_r_valid_o, axi_r_ready_i = 0;
  logic [47:0] reg_addr_i = 0;
  logic reg_write_i = 0;
  logic [31:0] reg_wdata_i = 0, reg_rdata_o;
  logic [3:0] reg_wstrb_i = 4'hf;
  logic reg_valid_i = 0, reg_error_o, reg_ready_o;
  logic rpc_clk_o, rpc_clk_no, rpc_cs_no, rpc_stb_o;
  logic phy_dqs_o, phy_dqs_n_o, phy_dqs_i, phy_dqs_n_i, device_dqs_oe;
  logic phy_dqs_pair_oe_o, phy_dqs_pair_ie_o, phy_dqs_pair_pd_en_o;
  logic [15:0] phy_db_o, phy_db_i;
  logic phy_db_oe_o, phy_db_ie_o, phy_db_pd_en_o;
  int ar_handshakes = 0;

  rpc_synth_wrap dut (.*);
  rpc_pin_memory device (
    .clk_i(rpc_clk_o), .rst_ni(rst_ni), .cs_ni(rpc_cs_no),
    .stb_i(rpc_stb_o), .db_i(phy_db_o), .db_oe_i(phy_db_oe_o),
    .dqs_oe_i(phy_dqs_pair_oe_o), .db_o(phy_db_i),
    .dqs_o(phy_dqs_i), .dqs_no(phy_dqs_n_i), .dqs_oe_o(device_dqs_oe)
  );
  rpc_timing_observe #(.REFRESH_ROW_STEP(1)) observe (
    .clk_i(rpc_clk_o), .rst_ni(rst_ni), .cs_ni(rpc_cs_no),
    .stb_i(rpc_stb_o), .db_i(phy_db_o), .db_oe_i(phy_db_oe_o)
  );
  always @(posedge clk_i) if (rst_ni) begin
    if (axi_ar_valid_i && axi_ar_ready_o) begin
      ar_handshakes = ar_handshakes + 1;
      $display("AXI_AR_HANDSHAKE time=%0t addr=%h", $time, axi_ar_addr_i);
    end
    if (axi_r_valid_o && axi_r_ready_i)
      $display("AXI_R_HANDSHAKE time=%0t data=%h", $time, axi_r_data_o);
  end

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

  task automatic axi_write(input logic [47:0] addr, input logic [63:0] data, input int beats);
    axi_write_mask(addr, data, beats, 8'hff, 0);
  endtask

  task automatic axi_write_mask(input logic [47:0] addr, input logic [63:0] data,
                                input int beats, input logic [7:0] strb,
                                input int bstall);
    axi_aw_addr_i = addr;
    axi_aw_len_i = beats - 1;
    axi_aw_valid_i = 1;
    $display("AXI_AW addr=%h beats=%0d strb=%h", addr, beats, strb);
    do @(posedge clk_i); while (!axi_aw_ready_o);
    @(negedge clk_i);
    axi_aw_valid_i = 0;
    for (int beat = 0; beat < beats; beat++) begin
      axi_w_data_i = data + beat;
      axi_w_strb_i = strb;
      axi_w_last_i = beat == beats - 1;
      axi_w_valid_i = 1;
      do @(posedge clk_i); while (!axi_w_ready_o);
      @(negedge clk_i);
    end
    axi_w_valid_i = 0;
    axi_w_last_i = 1;
    axi_w_strb_i = 8'hff;
    do @(negedge clk_i); while (!axi_b_valid_o);
    if (axi_b_resp_o != 0) $fatal(1, "AXI write response %0d", axi_b_resp_o);
    repeat (bstall) @(negedge clk_i);
    axi_b_ready_i = 1;
    @(posedge clk_i);
    @(negedge clk_i);
    axi_b_ready_i = 0;
  endtask

  task automatic axi_read(input logic [47:0] addr, input int beats, input logic [63:0] expected, input bit check);
    int prior;
    prior = ar_handshakes;
    @(negedge clk_i);
    axi_ar_addr_i = addr;
    axi_ar_len_i = beats - 1;
    axi_ar_valid_i = 1;
    $display("AXI_AR addr=%h beats=%0d", addr, beats);
    wait (ar_handshakes > prior);
    @(negedge clk_i);
    axi_ar_valid_i = 0;
    for (int beat = 0; beat < beats; beat++) begin
      do @(negedge clk_i); while (!axi_r_valid_o);
      if (check && axi_r_data_o != expected + beat)
        $fatal(1, "DATA_MISMATCH addr=%h beat=%0d got=%h expected=%h",
          addr, beat, axi_r_data_o, expected + beat);
      if (axi_r_last_o != (beat == beats - 1) || axi_r_resp_o != 0)
        $fatal(1, "AXI read protocol beat=%0d last=%b resp=%0d",
          beat, axi_r_last_o, axi_r_resp_o);
      axi_r_ready_i = 1;
      @(posedge clk_i);
      @(negedge clk_i);
      axi_r_ready_i = 0;
    end
  endtask

  task automatic axi_read_stalled(input logic [47:0] addr,
                                  input logic [63:0] expected,
                                  input logic [5:0] id,
                                  input int stall_cycles);
    int prior;
    logic [63:0] held_data;
    prior = ar_handshakes;
    @(negedge clk_i);
    axi_ar_addr_i = addr;
    axi_ar_len_i = 0;
    axi_ar_id_i = id;
    axi_ar_valid_i = 1;
    wait (ar_handshakes > prior);
    @(negedge clk_i);
    axi_ar_valid_i = 0;
    axi_ar_id_i = 0;
    do @(negedge clk_i); while (!axi_r_valid_o);
    held_data = axi_r_data_o;
    if (held_data != expected || axi_r_id_o != id || !axi_r_last_o || axi_r_resp_o != 0)
      $fatal(1, "AXI stalled read initial response addr=%h data=%h id=%h",
        addr, held_data, axi_r_id_o);
    repeat (stall_cycles) begin
      @(negedge clk_i);
      if (!axi_r_valid_o || axi_r_data_o != held_data || axi_r_id_o != id ||
          !axi_r_last_o || axi_r_resp_o != 0)
        $fatal(1, "AXI read response changed under backpressure addr=%h", addr);
    end
    axi_r_ready_i = 1;
    @(posedge clk_i);
    @(negedge clk_i);
    axi_r_ready_i = 0;
    $display("PASS AXI read backpressure addr=%h id=%h cycles=%0d", addr, id, stall_cycles);
  endtask

  task automatic direct_ref(input logic [31:0] cmd);
    int prior;
    prior = observe.refreshes;
    write_reg(8, cmd);
    while (observe.refreshes == prior) @(posedge clk_i);
    #0.001;
    if (!device_dqs_oe || !phy_dqs_i || !phy_dqs_n_i)
      $fatal(1, "REF BUSY did not drive both DQS pins high");
  endtask

  initial begin
    int v_init, v_func, prior;
    repeat (6) @(negedge clk_i);
    rst_ni = 1;
    for (int i = 0; i < 21; i++) write_reg(48'(36 + 4*i), 2);
    write_reg(36, 40000);
    write_reg(40, 1000);
    write_reg(44, 16);
    write_reg(48, 2);
    write_reg(56, 3);
    write_reg(60, 12);
    write_reg(64, 3);
    write_reg(68, 3);
    write_reg(76, 11);
    write_reg(84, 9);
    write_reg(104, 400);
    write_reg(24, 8);
    write_reg(28, 8);
    write_reg(32, 8);
    write_reg(0, 32'h04000000);
    wait (dut.i_rpc.i_rpc_controller.mgnmt_i_ctrl_o_init_flag);
    $display("SECTION init violations=%0d commands=%0d", observe.violations, observe.commands);
    v_init = observe.violations;

    axi_write(48'h100, 64'h1122334455667788, 1);
    axi_read(48'h100, 1, 64'h1122334455667788, 1);
    axi_read(48'h100, 1, 64'h1122334455667788, 1);
    axi_write(48'h800000, 64'h0101010101010101, 1);
    axi_read(48'h800000, 1, 64'h0101010101010101, 1);
    axi_write(48'h1000000, 64'h0202020202020202, 1);
    axi_read(48'h1000000, 1, 64'h0202020202020202, 1);
    axi_write(48'h1800000, 64'h0303030303030303, 1);
    axi_read(48'h1800000, 1, 64'h0303030303030303, 1);
    axi_write(48'h300, 64'haaaa000000000000, 1);
    axi_read(48'h400, 1, 64'h0, 0);
    axi_write(48'h500, 64'hcafe000000000000, 8);
    axi_read(48'h500, 8, 64'hcafe000000000000, 1);
    $display("SECTION functional violations=%0d commands=%0d", observe.violations, observe.commands);
    v_func = observe.violations;
    if (v_func != v_init)
      $fatal(1, "functional section added %0d timing violations", v_func - v_init);

    if ($test$plusargs("stress")) begin
      int accepted_before_r, posted;
      logic [47:0] post_addr [0:3];
      logic [63:0] post_data [0:3];
      logic [5:0] post_id [0:3];
      bit seen [0:3];
      accepted_before_r = 0;
      posted = 0;
      // Row conflict in bank 0. The controller uses byte address [24:23]
      // as the bank and [22:11] as the row.
      axi_write(48'h800, 64'h1111000000000001, 1);
      axi_write(48'h1000, 64'h2222000000000002, 1);
      axi_read(48'h800, 1, 64'h1111000000000001, 1);
      axi_read(48'h100, 1, 64'h1122334455667788, 1);
      axi_read(48'h1000, 1, 64'h2222000000000002, 1);
      // Four buffered reads. BufferDepth is 4. Count how many address
      // handshakes complete before any R beat is valid.
      post_addr[0] = 48'h100; post_data[0] = 64'h1122334455667788; post_id[0] = 1;
      post_addr[1] = 48'h800000; post_data[1] = 64'h0101010101010101; post_id[1] = 2;
      post_addr[2] = 48'h1000000; post_data[2] = 64'h0202020202020202; post_id[2] = 3;
      post_addr[3] = 48'h1800000; post_data[3] = 64'h0303030303030303; post_id[3] = 4;
      for (int i = 0; i < 4; i++) begin
        int prior, spins;
        prior = ar_handshakes;
        spins = 0;
        @(negedge clk_i);
        axi_ar_addr_i = post_addr[i];
        axi_ar_len_i = 0;
        axi_ar_id_i = post_id[i];
        axi_ar_valid_i = 1;
        spins = 0;
        while (ar_handshakes == prior && spins < 80) begin
          @(posedge clk_i);
          #0.001;
          spins++;
        end
        @(negedge clk_i);
        axi_ar_valid_i = 0;
        if (ar_handshakes == prior) begin
          $display("OUTSTANDING_AR index=%0d blocked spins=%0d rvalid=%b",
            i, spins, axi_r_valid_o);
          break;
        end
        if (!axi_r_valid_o) accepted_before_r++;
        posted++;
        $display("OUTSTANDING_AR index=%0d spins=%0d rvalid=%b accepted_before_r=%0d handshakes=%0d",
          i, spins, axi_r_valid_o, accepted_before_r, ar_handshakes - prior);
      end
      axi_ar_id_i = 0;
      for (int i = 0; i < 4; i++) seen[i] = 0;
      for (int n = 0; n < posted; n++) begin
        int match;
        do @(negedge clk_i); while (!axi_r_valid_o);
        match = -1;
        for (int i = 0; i < 4; i++)
          if (!seen[i] && axi_r_id_o == post_id[i]) match = i;
        if (match < 0 || axi_r_data_o != post_data[match] || !axi_r_last_o || axi_r_resp_o != 0)
          $fatal(1, "OUTSTANDING_DATA id=%h data=%h match=%0d last=%b resp=%0d",
            axi_r_id_o, axi_r_data_o, match, axi_r_last_o, axi_r_resp_o);
        seen[match] = 1;
        axi_r_ready_i = 1;
        @(posedge clk_i);
        @(negedge clk_i);
        axi_r_ready_i = 0;
      end
      for (int i = posted; i < 4; i++)
        axi_read(post_addr[i], 1, post_data[i], 1);
      $display("PASS outstanding reads posted_without_drain=%0d accepted_before_r=%0d",
        posted, accepted_before_r);
      // Alternating banks, with B-channel backpressure on the writes.
      for (int k = 0; k < 4; k++) begin
        logic [47:0] addr;
        logic [63:0] data;
        addr = (48'(k) << 23) | 48'h2000;
        data = 64'hA500000000000000 + k;
        axi_write_mask(addr, data, 1, 8'hff, 4);
        axi_read(addr, 1, data, 1);
      end
      // A 4-byte WSTRB is checked against preserved upper bytes. The pin
      // write mask for this beat is recorded in the log.
      axi_write_mask(48'h100, 64'h00000000AABBCCDD, 1, 8'h0f, 0);
      begin
        logic [63:0] masked;
        int prior;
        prior = ar_handshakes;
        @(negedge clk_i);
        axi_ar_addr_i = 48'h100;
        axi_ar_len_i = 0;
        axi_ar_valid_i = 1;
        wait (ar_handshakes > prior);
        @(negedge clk_i);
        axi_ar_valid_i = 0;
        do @(negedge clk_i); while (!axi_r_valid_o);
        masked = axi_r_data_o;
        axi_r_ready_i = 1;
        @(posedge clk_i);
        @(negedge clk_i);
        axi_r_ready_i = 0;
        $display("MASK_READBACK data=%h full_overwrite=%b low_bytes_only=%b",
          masked, masked == 64'h00000000AABBCCDD,
          masked == 64'h11223344AABBCCDD);
      end
      if (observe.violations != v_func)
        $fatal(1, "stress traffic added %0d timing violations", observe.violations - v_func);
      $display("PASS eth stress traffic commands=%0d", observe.commands);
      $finish;
    end

    if ($test$plusargs("negative_refresh") || $test$plusargs("borderline_refresh")) begin
      // N_REF=2 produces REF+16, early under either reading. N_REF=20
      // clears one tREFI after the controller's packet alignment, but is
      // still early under the row-step reading.
      // Stop after the ACT so the two refresh interpretations stay separate.
      write_reg(100, $test$plusargs("borderline_refresh") ? 20 : 2);
      direct_ref(32'h04000000);
      prior = ar_handshakes;
      @(negedge clk_i);
      axi_ar_addr_i = 48'h100;
      axi_ar_valid_i = 1;
      wait (ar_handshakes > prior);
      @(negedge clk_i);
      axi_ar_valid_i = 0;
      wait (observe.violations > v_func);
      $display("PASS expected REF interpretation violation count=%0d borderline=%0d",
        observe.violations - v_func, $test$plusargs("borderline_refresh"));
      $finish;
    end

    axi_read_stalled(48'h100, 64'h1122334455667788, 6'h2a, 7);

    // Etron section 5 describes one-shot refresh as one pass over selected
    // rows. These row-step waits are the selected, documented interpretation.
    write_reg(100, 81920);  // one bank: 4096 rows * 20 CK
    write_reg(96, 163840);  // two banks
    write_reg(92, 245760);  // three banks
    write_reg(88, 327680);  // four banks
    direct_ref(32'h04000000);
    axi_read(48'h100, 1, 64'h1122334455667788, 1);
    direct_ref(32'h0C000000);
    axi_read(48'h100, 1, 64'h1122334455667788, 1);
    direct_ref(32'h3C000000);
    wait (device.cycle >= device.refresh_busy_until);
    #0.001;
    if (!device_dqs_oe || phy_dqs_i || phy_dqs_n_i)
      $fatal(1, "REF completion low pulse missing");
    wait (device.cycle >= device.refresh_busy_until + 1);
    #0.001;
    if (device_dqs_oe)
      $fatal(1, "REF completion did not release DQS pins cycle=%0d busy_until=%0d read_active=%0d",
        device.cycle, device.refresh_busy_until, device.read_active);
    axi_read(48'h1800000, 1, 64'h0303030303030303, 1);
    if (observe.violations != v_func)
      $fatal(1, "programmed REF added %0d timing violations", observe.violations - v_func);
    $display("PASS eth directed timing with 1, 2, and 4-bank refresh");
    $finish;
  end

  initial begin
    #20_000_000;
    $fatal(1, "directed ETH timing test timeout");
  end
endmodule
