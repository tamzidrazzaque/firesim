// Check the ETH Zurich rpc_cmd_decoder against the command-word layout
// documented from rpc_cmd_fsm.sv. This instantiates their decoder; it does
// not modify it. It is a command-encoding test, not a PHY or data test.
`timescale 1ns/1ps

module tb_eth_cmd_decoder;
  logic [31:0] cmd;
  logic [3:0]  decoded;
  logic [5:0]  burst;
  logic [1:0]  zqc;
  logic [3:0]  ref_banks;
  int errors;

  rpc_cmd_decoder dut (
    .cmd_i(cmd),
    .cmd_decoded_o(decoded),
    .burst_length_o(burst),
    .zqc_mode_o(zqc),
    .ref_bank_num_o(ref_banks)
  );

  // Opcode values from rpc_cmd_pkg.sv
  localparam CMD_RESET = 4'd1;
  localparam CMD_PRE   = 4'd2;
  localparam CMD_MRS   = 4'd3;
  localparam CMD_ACT   = 4'd4;
  localparam CMD_WR    = 4'd5;
  localparam CMD_RD    = 4'd6;
  localparam CMD_REF   = 4'd7;
  localparam CMD_ZQC   = 4'd8;

  task check(input string name, input [3:0] exp);
    begin
      #1;
      if (decoded !== exp) begin
        $display("FAIL %s decoded=%0d expected=%0d cmd=%h", name, decoded, exp, cmd);
        errors = errors + 1;
      end else begin
        $display("PASS %s cmd=%h", name, cmd);
      end
    end
  endtask

  initial begin
    errors = 0;
    // ACT bank=2 row=0xABC. Layout from rpc_cmd_fsm.sv:
    // {11'b0, BA, 3'b101, 3'b000, row, 1'b0}
    cmd = {11'b0, 2'b10, 3'b101, 3'b000, 12'hABC, 1'b0};
    check("ACT", CMD_ACT);

    // RD bank=1, BC=0, CA group 0x13 -> CA[6:4]=3, CA[9:7]=2
    // {CA[6:4], 2'b0, BC, BA, 3'b000, CA[9:7], 12'b0, 1'b0}
    cmd = {3'd3, 2'b0, 6'd0, 2'b01, 3'b000, 3'd2, 12'b0, 1'b0};
    check("RD", CMD_RD);
    if (burst !== 6'd0) begin
      $display("FAIL RD burst=%0d", burst);
      errors = errors + 1;
    end

    // WR BC=3. n_words = BC+1 = 4 in our model; the decoder returns the field.
    cmd = {3'd0, 2'b0, 6'd3, 2'b00, 3'b001, 3'd0, 12'b0, 1'b0};
    check("WR", CMD_WR);
    if (burst !== 6'd3) begin
      $display("FAIL WR burst=%0d", burst);
      errors = errors + 1;
    end

    // PRE banks 0 and 2 (mask 0101). Decoder does not return the mask; it
    // classifies the opcode. Mask bits sit at [25:22].
    cmd = {6'b0, 4'b0101, 3'b000, 3'b100, 15'b0, 1'b0};
    check("PRE", CMD_PRE);

    // REF all banks. ref_bank_num is the popcount of [25:22].
    cmd = {6'b0, 4'b1111, 3'b000, 3'b110, 15'b0, 1'b0};
    check("REF", CMD_REF);
    if (ref_banks !== 4'd4) begin
      $display("FAIL REF popcount=%0d", ref_banks);
      errors = errors + 1;
    end

    // ZQC: opcode 001 and bit 0 set. Mode in [31:30].
    cmd = {2'b10, 11'b0, 3'b001, 15'b0, 1'b1};
    check("ZQC", CMD_ZQC);
    if (zqc !== 2'b10) begin
      $display("FAIL ZQC mode=%b", zqc);
      errors = errors + 1;
    end

    cmd = {1'b0, 12'b0, 3'b000, 15'b0, 1'b1};
    check("RESET", CMD_RESET);

    if (errors == 0) begin
      $display("ALL PASS");
      $finish;
    end else begin
      $display("FAILED %0d", errors);
      $fatal(1);
    end
  end
endmodule
