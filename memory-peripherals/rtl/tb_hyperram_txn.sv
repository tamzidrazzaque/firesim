// Directed checks for hyperram_txn. Expected latency is CA + 2*LAT = 17
// for the fixed-latency power-on default, matching the Python model.
`timescale 1ns/1ps

module tb_hyperram_txn;
  logic clk = 0;
  logic rst_n = 0;
  always #5 clk = ~clk;

  logic        req_valid, req_ready, req_write, req_wstrb, resp_valid;
  logic [24:0] req_addr;
  logic [7:0]  req_wdata, resp_rdata;
  logic [15:0] resp_latency;
  int errors;
  int cycles;

  hyperram_txn dut (
    .clk(clk), .rst_n(rst_n),
    .req_valid(req_valid), .req_ready(req_ready),
    .req_write(req_write), .req_addr(req_addr),
    .req_wdata(req_wdata), .req_wstrb(req_wstrb),
    .resp_valid(resp_valid), .resp_rdata(resp_rdata),
    .resp_latency(resp_latency)
  );

  task automatic tick;
    begin
      @(posedge clk);
      #1;
    end
  endtask

  initial begin
    errors = 0;
    req_valid = 0;
    req_write = 0;
    req_wstrb = 0;
    req_addr = 0;
    req_wdata = 0;
    repeat (4) tick();
    rst_n = 1;
    tick();

    // Write 0xA5 to address 4, strobe on.
    req_valid = 1;
    req_write = 1;
    req_wstrb = 1;
    req_addr = 25'd4;
    req_wdata = 8'hA5;
    tick();
    req_valid = 0;
    cycles = 0;
    while (!resp_valid) begin
      tick();
      cycles = cycles + 1;
    end
    if (resp_latency !== 16'd17 || cycles !== 17) begin
      $display("FAIL write latency reg=%0d cycles=%0d", resp_latency, cycles);
      errors = errors + 1;
    end else $display("PASS write latency %0d", cycles);

    // One idle cycle, then read it back.
    tick();
    req_valid = 1;
    req_write = 0;
    req_addr = 25'd4;
    tick();
    req_valid = 0;
    cycles = 0;
    while (!resp_valid) begin
      tick();
      cycles = cycles + 1;
    end
    if (resp_rdata !== 8'hA5 || cycles !== 17) begin
      $display("FAIL read data=%h cycles=%0d", resp_rdata, cycles);
      errors = errors + 1;
    end else $display("PASS read data");

    // Masked write must leave the byte alone.
    req_valid = 1;
    req_write = 1;
    req_wstrb = 0;
    req_wdata = 8'hFF;
    req_addr = 25'd4;
    tick();
    req_valid = 0;
    while (!resp_valid) tick();
    tick();
    req_valid = 1;
    req_write = 0;
    tick();
    req_valid = 0;
    while (!resp_valid) tick();
    if (resp_rdata !== 8'hA5) begin
      $display("FAIL mask data=%h", resp_rdata);
      errors = errors + 1;
    end else $display("PASS masked write");

    if (errors == 0) begin
      $display("ALL PASS");
      $finish;
    end else begin
      $display("FAILED %0d", errors);
      $fatal(1);
    end
  end
endmodule
