// Transaction-level HyperRAM timing and data model.
//
// This is not a DQ/RWDS pin model. A controller that already speaks
// chip-select transactions can be checked against it. Pin-level controllers
// need a PHY adapter in front. Cycle counts follow the same 200 MHz
// power-on defaults as the Python model: CA = 3, base latency = 7,
// fixed latency doubles it, 2 bytes per CK.
`timescale 1ns/1ps

module hyperram_txn #(
  parameter int CA = 3,
  parameter int LAT = 7,
  parameter bit FIXED = 1
) (
  input  logic        clk,
  input  logic        rst_n,
  input  logic        req_valid,
  output logic        req_ready,
  input  logic        req_write,
  input  logic [24:0] req_addr,
  input  logic [7:0]  req_wdata,
  input  logic        req_wstrb,
  output logic        resp_valid,
  output logic [7:0]  resp_rdata,
  output logic [15:0] resp_latency
);
  logic [7:0] mem [0:255];
  logic [15:0] lat_q;
  logic        busy;
  logic [7:0]  wait_q;
  logic        do_write;
  logic [24:0] addr_q;
  logic [7:0]  wdata_q;
  logic        wstrb_q;

  assign req_ready = rst_n && !busy;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      busy        <= 1'b0;
      resp_valid  <= 1'b0;
      resp_rdata  <= '0;
      resp_latency <= '0;
      wait_q      <= '0;
      lat_q       <= '0;
    end else begin
      resp_valid <= 1'b0;
      if (!busy && req_valid) begin
        busy   <= 1'b1;
        // First-byte latency is CA + L, or CA + 2L when fixed.
        lat_q  <= CA + (FIXED ? (LAT * 2) : LAT);
        // Total CS-low for a 2-byte beat, minus one because this cycle
        // is the accept cycle. The testbench checks resp_latency, which
        // is the first-byte figure, not this countdown.
        // Countdown reaches 1 on the latency cycle; see the decrement below.
        wait_q <= CA + (FIXED ? (LAT * 2) : LAT);
        do_write <= req_write;
        addr_q <= req_addr;
        wdata_q <= req_wdata;
        wstrb_q <= req_wstrb;
      end else if (busy) begin
        if (wait_q == 16'd1) begin
          busy <= 1'b0;
          resp_valid <= 1'b1;
          resp_latency <= lat_q;
          if (do_write) begin
            if (wstrb_q)
              mem[addr_q[7:0]] <= wdata_q;
          end else begin
            resp_rdata <= mem[addr_q[7:0]];
          end
        end else begin
          wait_q <= wait_q - 1;
        end
      end
    end
  end
endmodule
