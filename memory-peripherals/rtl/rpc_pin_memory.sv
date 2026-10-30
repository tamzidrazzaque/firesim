`timescale 1ns/1ps

// Digital RPC DRAM device for the 200 MHz CL=8 test configuration. It observes
// the external packet, mask and data pins. Timing and geometry follow Etron
// EM6GA16L Rev. 1.4, sections 2.4-2.7, 3.3, 7 and table 11-3.
module rpc_pin_memory #(
  parameter bit REFRESH_ROW_STEP = 1,
  parameter bit FATAL_ON_REFRESH_BUSY = 0,
  parameter int ROWS = 4096,
  parameter int TREFI_FST = 20,
  parameter int TREFI_LP = 640,
  parameter int TRFQSL_CK = 1, // tRFQSL >= 5 ns at the 200 MHz PHY clock
  parameter bit CASE_TEMP_GT85 = 0
) (
  input logic clk_i,
  input logic rst_ni,
  input logic cs_ni,
  input logic stb_i,
  input logic [15:0] db_i,
  input logic db_oe_i,
  input logic dqs_oe_i,
  output logic [15:0] db_o,
  output logic dqs_o,
  output logic dqs_no,
  output logic dqs_oe_o
);
  logic [255:0] words [0:(1<<20)-1];
  logic row_open [0:3];
  logic [11:0] open_row [0:3];
  int last_act [0:3];
  int last_pre [0:3];
  int cycle = 0;
  logic prev_stb = 1;
  int command_wait = -1;
  logic command_fall = 0;
  logic [15:0] command_rise;
  logic [31:0] command;
  logic [1:0] access_bank;
  logic [11:0] access_row;
  logic [5:0] access_col;
  int access_words;
  int phase = -1;
  logic write_active = 0;
  logic read_active = 0;
  logic [31:0] first_mask, last_mask;
  logic [15:0] sample_rise;
  int acts = 0, pres = 0, writes = 0, reads = 0;
  logic [2:0] init_stage;
  int reset_packet_cycle, mrs_cycle, zqc_cycle;
  int refresh_busy_until = -1;

  // Section 5: both strobes are high during one-shot REF BUSY, then both
  // pulse low for tRFQSL before being released. A pad wrapper uses dqs_oe_o
  // for the Hi-Z state; the existing Chipyard harness consumes only values.
  // The row-step duration is an explicit interpretation of the unnumbered
  // internal loop, and can be overridden by REFRESH_ROW_STEP.
  wire ref_busy = (refresh_busy_until >= 0 && cycle < refresh_busy_until);
  wire ref_low = (refresh_busy_until >= 0 && cycle >= refresh_busy_until &&
                  cycle < refresh_busy_until + TRFQSL_CK);
  assign dqs_oe_o = ref_busy || ref_low || read_active;
  assign dqs_o = ref_busy ? 1'b1 : (ref_low ? 1'b0 : (read_active ? clk_i : 1'b0));
  assign dqs_no = ref_busy ? 1'b1 : (ref_low ? 1'b0 : ~dqs_o);

  function automatic int word_index(input int word_number);
    word_index = (int'(access_bank) << 18) | (int'(access_row) << 6) |
      ((int'(access_col) + word_number) & 63);
  endfunction

  // One process owns state updated on both clock edges. The rising edge
  // samples the first DB half-word; the falling edge assembles the packet.
  always @(posedge clk_i or negedge clk_i) begin
    if (clk_i) begin
    if (!rst_ni) begin
      cycle <= 0;
      prev_stb <= 1;
      command_wait <= -1;
      command_fall <= 0;
      write_active <= 0;
      read_active <= 0;
      phase <= -1;
      init_stage <= 0;
      reset_packet_cycle <= -1;
      mrs_cycle <= -1;
      zqc_cycle <= -1;
      refresh_busy_until <= -1;
      for (int b = 0; b < 4; b++) begin
        row_open[b] <= 0;
        last_act[b] <= -1000;
        last_pre[b] <= -1000;
      end
    end else begin
      cycle <= cycle + 1;
      prev_stb <= stb_i;
      if (cs_ni == 0 && prev_stb && !stb_i && command_wait < 0)
        command_wait <= 2;
      else if (command_wait > 0)
        command_wait <= command_wait - 1;
      if (command_wait == 2 && stb_i)
        $fatal(1,"RPC STB must stay low for two clocks before a parallel packet");
      if (command_wait == 1) begin
        if (!db_oe_i) $fatal(1, "RPC command packet not driven at cycle %0d", cycle);
        command_rise <= db_i;
        command_fall <= 1;
        command_wait <= -1;
      end
      if (write_active || read_active || phase >= 0) phase <= phase + 1;
      // phase advances at this edge; the PHY drives the next half-cycle's
      // value before the matching falling edge samples it.
      if (write_active && phase >= 6 && phase < 8 + 8*access_words) begin
        if (!db_oe_i || !dqs_oe_i)
          $fatal(1, "RPC write mask/data not driven at phase %0d", phase);
        sample_rise <= db_i;
      end
      if (read_active && phase >= 8 && phase < 8 + 8*access_words) begin
        int pos;
        pos = phase - 8;
        db_o <= words[word_index(pos / 8)][(pos % 8)*32 +: 16];
      end
      if (phase == 9 + 8*access_words && write_active) begin
        write_active <= 0;
        phase <= -1;
      end
    end
    end else begin
    if (rst_ni) begin
      if (command_fall) begin
        int bank;
        logic [31:0] packet;
        packet = {command_rise, db_i};
        if (!db_oe_i) $fatal(1,"RPC command falling half not driven");
        command = packet;
        command_fall <= 0;
        bank = int'(packet[20:19]);
        $display("RPC_PIN_CMD cycle=%0d packet=%h op=%0d bank=%0d",cycle,packet,packet[18:16],bank);
        if (cycle < refresh_busy_until && packet != 32'h00000001 && FATAL_ON_REFRESH_BUSY)
          $fatal(1, "RPC command during refresh at %0d, busy until %0d",
            cycle, refresh_busy_until);
        case (init_stage)
          0: begin
            if (packet != 32'h00000001 || cycle < 40000)
              $fatal(1,"RPC RESET packet or 200us stable-clock delay missing");
            reset_packet_cycle <= cycle;
            init_stage <= 1;
          end
          1: begin
            if (packet[18:16] != 3'b100 || cycle-reset_packet_cycle < 1000)
              $fatal(1,"RPC PRE or 5us post-RESET delay missing");
            init_stage <= 2;
          end
          2: begin
            if (packet != 32'h04020000)
              $fatal(1,"RPC CL8 MRS packet missing");
            mrs_cycle <= cycle;
            init_stage <= 3;
          end
          3: begin
            if (packet != 32'h00010001 || cycle-mrs_cycle < 12)
              $fatal(1,"RPC ZQINIT packet or tMOD delay missing");
            zqc_cycle <= cycle;
            init_stage <= 4;
          end
          default: ;
        endcase
        case (packet[18:16])
          3'b101: begin
            if (init_stage != 4 || cycle-zqc_cycle < 400)
              $fatal(1,"RPC ACT before 2us ZQINIT completion");
            if (row_open[bank]) $fatal(1, "ACT to open bank %0d",bank);
            if (cycle - last_pre[bank] < 3) $fatal(1,"tRP bank %0d",bank);
            row_open[bank] <= 1;
            open_row[bank] <= packet[12:1];
            last_act[bank] <= cycle;
            acts <= acts + 1;
          end
          3'b100: begin
            for (int b = 0; b < 4; b++) if (packet[22+b]) begin
              if (row_open[b] && cycle - last_act[b] < 7)
                $fatal(1,"tRAS bank %0d",b);
              row_open[b] <= 0;
              last_pre[b] <= cycle;
              pres <= pres + 1;
            end
          end
          3'b001, 3'b000: if (!packet[0]) begin
            if (!row_open[bank] || cycle - last_act[bank] < 3)
              $fatal(1,"CAS without legal ACT bank %0d",bank);
            access_bank <= 2'(bank);
            access_row <= open_row[bank];
            access_col <= {packet[15:13],packet[31:29]};
            access_words <= int'(packet[26:21]) + 1;
            phase <= 0;
            if (packet[18:16] == 3'b001) begin
              write_active <= 1;
              writes <= writes + 1;
            end else begin
              reads <= reads + 1;
            end
          end
          3'b110: begin
            int banks, step, mask;
            mask = int'(packet[25:22]);
            banks = $countones(packet[25:22]);
            if (banks == 0) $fatal(1, "RPC REF selects no bank");
            if (packet[2]) $fatal(1, "RPC REFOP1 reserved");
            if (CASE_TEMP_GT85 && packet[1] && banks > 2)
              $fatal(1, "RPC LP REF above 85C selects more than two banks");
            step = packet[2:1] == 2'b01 ? TREFI_LP : TREFI_FST;
            refresh_busy_until <= cycle +
              (REFRESH_ROW_STEP ? ROWS * step * banks : step);
            // One-shot refresh precharges all banks, then refreshes only the
            // selected banks (Rev. 1.4 section 5.1).
            for (int b = 0; b < 4; b++) row_open[b] <= 0;
            $display("RPC_PIN_REFRESH cycle=%0d banks=%0d busy_until=%0d",
              cycle, banks,
              cycle + (REFRESH_ROW_STEP ? ROWS * step * banks : step));
          end
          default: ;
        endcase
      end
      if (write_active && phase >= 7 && phase < 9 + 8*access_words) begin
        logic [31:0] packet;
        packet = {db_i,sample_rise};
        if (phase == 7) first_mask <= packet;
        else if (phase == 8) last_mask <= packet;
        else begin
          int pos, idx, mask;
          pos = phase - 9;
          idx = word_index(pos / 8);
          mask = (pos / 8 == 0) ? first_mask :
                 ((pos / 8 == access_words - 1) ? last_mask : 0);
          if (pos % 8 == 0)
            $display("RPC_PIN_WRITE cycle=%0d bank=%0d row=%0d col=%0d idx=%0d mask=%h first=%h",
              cycle, access_bank, access_row, access_col + pos/8, idx, mask, packet);
          for (int b = 0; b < 4; b++)
            if (!mask[(pos % 8)*4+b]) words[idx][(pos % 8)*32+b*8 +: 8] <= packet[b*8 +: 8];
        end
      end
      if (phase == 8 && !write_active && !read_active && access_words > 0) begin
        read_active <= 1;
      end
      if (read_active && phase >= 9 && phase < 9 + 8*access_words) begin
        int pos;
        pos = phase - 9;
        db_o <= words[word_index(pos / 8)][(pos % 8)*32+16 +: 16];
        if (pos % 8 == 0)
          $display("RPC_PIN_READ cycle=%0d bank=%0d row=%0d col=%0d idx=%0d first=%h",
            cycle, access_bank, access_row, access_col + pos/8,
            word_index(pos/8), words[word_index(pos/8)][31:0]);
        if (phase == 8 + 8*access_words) begin
          read_active <= 0;
          phase <= -1;
        end
      end
    end
    end
  end
endmodule
