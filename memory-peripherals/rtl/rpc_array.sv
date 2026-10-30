// Four-bank RPC DRAM array with tRCD checking.
// Command opcodes match rpc_cmd_pkg: ACT=4, RD=6, WR=5, PRE=2.
// A read or write before tRCD raises error and returns 0.
`timescale 1ns/1ps

module rpc_array #(
  parameter int TRCD = 11,
  parameter int RL = 12
) (
  input  logic        clk,
  input  logic        rst_n,
  input  logic        cmd_valid,
  output logic        cmd_ready,
  input  logic [3:0]  cmd_op,
  input  logic [1:0]  cmd_bank,
  input  logic [11:0] cmd_row,
  input  logic [7:0]  cmd_wdata,
  output logic        resp_valid,
  output logic [7:0]  resp_rdata,
  output logic        error
);
  localparam OP_PRE = 4'd2;
  localparam OP_ACT = 4'd4;
  localparam OP_WR  = 4'd5;
  localparam OP_RD  = 4'd6;

  logic        open_q [0:3];
  logic [11:0] row_q  [0:3];
  logic [7:0]  age_q  [0:3];
  logic [7:0]  mem [0:3][0:15];

  assign cmd_ready = rst_n;

  integer b;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      resp_valid <= 1'b0;
      resp_rdata <= '0;
      error <= 1'b0;
      for (b = 0; b < 4; b++) begin
        open_q[b] <= 1'b0;
        row_q[b] <= '0;
        age_q[b] <= '0;
      end
    end else begin
      resp_valid <= 1'b0;
      error <= 1'b0;
      for (b = 0; b < 4; b++) begin
        if (open_q[b] && age_q[b] != 8'hff)
          age_q[b] <= age_q[b] + 1;
      end
      if (cmd_valid) begin
        unique case (cmd_op)
          OP_ACT: begin
            open_q[cmd_bank] <= 1'b1;
            row_q[cmd_bank] <= cmd_row;
            age_q[cmd_bank] <= 8'd0;
          end
          OP_PRE: begin
            open_q[cmd_bank] <= 1'b0;
          end
          OP_WR: begin
            if (!open_q[cmd_bank] || age_q[cmd_bank] < TRCD) begin
              error <= 1'b1;
            end else begin
              mem[cmd_bank][cmd_row[3:0]] <= cmd_wdata;
            end
          end
          OP_RD: begin
            resp_valid <= 1'b1;
            if (!open_q[cmd_bank] || age_q[cmd_bank] < TRCD) begin
              error <= 1'b1;
              resp_rdata <= '0;
            end else begin
              resp_rdata <= mem[cmd_bank][row_q[cmd_bank][3:0]];
            end
          end
          default: error <= 1'b1;
        endcase
      end
    end
  end
endmodule
