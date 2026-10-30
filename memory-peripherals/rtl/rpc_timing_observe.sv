`timescale 1ns/1ps

// Online RPC timing observer. It watches the same pins as rpc_pin_memory and
// prints a violation on the cycle the packet is assembled. It has no ready
// output, so it cannot delay a controller command until the command is legal.
//
// REFRESH_ROW_STEP selects the Section 5 reading:
//   0: one-shot busy window is one tREFI
//   1: one-shot busy window is rows * tREFI * selected banks
// The datasheet does not name tRFC. Both readings stay available.
module rpc_timing_observe #(
  parameter int REFRESH_ROW_STEP = 1,
  parameter int ROWS = 4096,
  parameter int TRCD = 3,
  parameter int TRP = 3,
  parameter int TRAS = 7,
  parameter int TRC = 10,
  parameter int TRRD = 2,
  parameter int TWR = 3,
  parameter int TPPD_IDLE = 4,
  parameter int TPPD_ACT = 8,
  parameter int TREFI_FST = 20,
  parameter int TREFI_LP = 640,
  parameter bit CASE_TEMP_GT85 = 0,
  parameter int TPOWERUP = 40000,
  parameter int TRESET = 1000,
  parameter int TMOD = 12,
  parameter int TZQINIT = 400,
  parameter bit FATAL_ON_VIOLATION = 0
) (
  input logic clk_i,
  input logic rst_ni,
  input logic cs_ni,
  input logic stb_i,
  input logic [15:0] db_i,
  input logic db_oe_i
);
  int cycle;
  int command_wait;
  logic command_fall;
  logic prev_stb;
  logic [15:0] command_rise;
  int phase; // 0 powerup, 1 reset-busy, 2 need PRE, 3 need MRS, 4 ready
  int busy_until;
  string busy_name;
  int last_cmd;
  int last_act_any;
  int mrs_cycle;
  int rl;
  int nwr;
  int turn;
  int row_open [0:3];
  int act_at [0:3];
  int pre_at [0:3];
  int rd_at [0:3];
  int rd_ck [0:3];
  int wr_at [0:3];
  int wr_ck [0:3];
  int col_at;
  int col_ck;
  int col_kind;
  int violations;
  int commands;
  int refreshes;
  bit zq_seen;

  function automatic int popcount4(input int mask);
    popcount4 = ((mask >> 0) & 1) + ((mask >> 1) & 1) +
                ((mask >> 2) & 1) + ((mask >> 3) & 1);
  endfunction

  function automatic int any_open();
    any_open = row_open[0] | row_open[1] | row_open[2] | row_open[3];
  endfunction

  task automatic violate(input string name, input int earliest, input string detail);
    violations += 1;
    $display("RPC_TIMING_VIOLATION constraint=%s offered=%0d earliest=%0d %s",
      name, cycle, earliest, detail);
    if (FATAL_ON_VIOLATION) $fatal(1, "RPC %s", name);
  endtask

  always @(posedge clk_i or negedge clk_i) begin
    if (clk_i) begin
      if (!rst_ni) begin
        cycle <= 0;
        command_wait <= -1;
        command_fall <= 0;
        prev_stb <= 1;
      end else begin
        cycle <= cycle + 1;
        prev_stb <= stb_i;
        if (cs_ni == 0 && prev_stb && !stb_i && command_wait < 0)
          command_wait <= 2;
        else if (command_wait > 0)
          command_wait <= command_wait - 1;
        if (command_wait == 1) begin
          command_rise <= db_i;
          command_fall <= 1;
          command_wait <= -1;
        end
      end
    end else if (!rst_ni) begin
      phase = 0;
      busy_until = 0;
      busy_name = "tRESET";
      last_cmd = -100000;
      last_act_any = -100000;
      mrs_cycle = -100000;
      rl = 9;
      nwr = 4;
      turn = 8;
      col_at = -100000;
      col_ck = 0;
      col_kind = 0;
      violations = 0;
      commands = 0;
      refreshes = 0;
      zq_seen = 0;
      for (int b = 0; b < 4; b++) begin
        row_open[b] = 0;
        act_at[b] = -100000;
        pre_at[b] = -100000;
        rd_at[b] = -100000;
        rd_ck[b] = 0;
        wr_at[b] = -100000;
        wr_ck[b] = 0;
      end
    end else if (command_fall) begin
      int packet, rise, fall, op, bank, mask, nbank, window, clocks, gap;
      int phase_now, open_now, rejected, v_before;
      command_fall <= 0;
      packet = {command_rise, db_i};
      rise = packet[31:16];
      fall = packet[15:0];
      op = rise & 7;
      bank = (rise >> 3) & 3;
      commands += 1;
      phase_now = phase;
      rejected = 0;
      v_before = violations;
      if (busy_until != 0 && cycle >= busy_until) begin
        busy_until = 0;
        if (phase == 1) phase_now = 2;
      end
      open_now = any_open();
      gap = open_now ? TPPD_ACT : TPPD_IDLE;
      // Rev. 1.4 section 2.8 says active-state parallel command intervals
      // are 8 tCK or an integer multiple, not merely at least 8 tCK.
      if (phase_now == 4 && zq_seen && open_now && last_cmd > -1000 &&
          cycle >= last_cmd + TPPD_ACT &&
          (cycle - last_cmd) % TPPD_ACT != 0 &&
          !(op == 0 && fall == 1 && rise == 0))
        violate("tPPD_grid", last_cmd +
          ((cycle - last_cmd + TPPD_ACT - 1) / TPPD_ACT) * TPPD_ACT,
          "active-state parallel command is off the 8-CK grid");

      if (op == 0 && fall == 1 && rise == 0) begin
        if (phase == 0 && cycle < TPOWERUP)
          violate("powerup", TPOWERUP, "RESET v_before 200 us stable clock");
        if (violations == v_before) begin
          phase = 1;
          busy_until = cycle + TRESET;
          busy_name = "tRESET";
          last_cmd = cycle;
          for (int b = 0; b < 4; b++) row_open[b] = 0;
          zq_seen = 0;
        end
      end else if (busy_until != 0 && cycle < busy_until) begin
        violate(busy_name, busy_until, "command while the device is busy");
        rejected = 1;
      end else if (op == 4) begin
        mask = (rise >> 6) & 15;
        if (last_cmd > -1000 && cycle < last_cmd + gap)
          violate("tPPD", last_cmd + gap, "PRE");
        if (mask == 0) violate("bank_mask", cycle, "PRE selects no bank");
        if (phase_now == 2) begin
          if (mask != 15) violate("init_PRE_ALL", cycle, "initial PRE must select all banks");
        end else if (phase_now != 4 || !zq_seen)
          violate("init_order", cycle, "PRE v_before RESET/PRE/MRS/ZQ");
        else for (int b = 0; b < 4; b++) if (mask[b]) begin
          int legal;
          if (!row_open[b])
            violate("require_active_bank", cycle, $sformatf("bank %0d idle", b));
          else begin
            legal = act_at[b] + TRAS;
            if (rd_at[b] > -1000 && rd_at[b] + rl + rd_ck[b] > legal)
              legal = rd_at[b] + rl + rd_ck[b];
            if (wr_at[b] > -1000) begin
              int wr_legal;
              wr_legal = wr_at[b] + rl + wr_ck[b] + ((nwr > TWR) ? nwr : TWR);
              if (wr_legal > legal) legal = wr_legal;
            end
            if (cycle < legal)
              violate((rd_at[b] > wr_at[b]) ? "read_to_precharge" : "tRAS",
                legal, $sformatf("bank %0d", b));
          end
        end
        if (violations == v_before) begin
          for (int b = 0; b < 4; b++) if (mask[b]) begin
            row_open[b] = 0;
            pre_at[b] = cycle;
          end
          last_cmd = cycle;
          phase = phase_now == 2 ? 3 : 4;
        end
      end else if (op == 2) begin
        int cl_code, nwr_code, cl_val, new_nwr;
        cl_code = (rise >> 3) & 7;
        nwr_code = (rise >> 6) & 7;
        cl_val = 8;
        if (cl_code == 1) cl_val = 10;
        else if (cl_code == 2) cl_val = 11;
        else if (cl_code == 6) cl_val = 3;
        else if (cl_code != 0) violate("MRS_CL_reserved", cycle, "reserved CL code");
        case (nwr_code)
          0: new_nwr = 4;
          1: new_nwr = 6;
          2: new_nwr = 7;
          3: new_nwr = 8;
          4: new_nwr = 10;
          5: new_nwr = 12;
          6: new_nwr = 14;
          default: new_nwr = 16;
        endcase
        if (new_nwr < TWR) violate("MRS_nWR", cycle, "nWR below tWR");
        if (((rise >> 9) & 15) == 0) violate("MRS_Zout", cycle, "output is disabled");
        if (phase_now != 3 && (phase_now != 4 || !zq_seen))
          violate("init_order", cycle, "MRS v_before RESET and PRE ALL");
        if (any_open()) violate("MRS_bank_open", cycle, "all banks must be idle");
        if (last_cmd > -1000 && cycle < last_cmd + TPPD_IDLE)
          violate("tPPD", last_cmd + TPPD_IDLE, "MRS");
        if (violations == v_before) begin
          rl = cl_val + 1;
          nwr = new_nwr;
          turn = (cl_val == 3) ? 0 : 8;
          phase = 4;
          mrs_cycle = cycle;
          last_cmd = cycle;
        end
      end else if (op == 1 && (fall & 1)) begin
        if (phase_now != 4 || mrs_cycle < 0)
          violate("init_order", cycle, "ZQ v_before MRS");
        if (mrs_cycle > -1000 && cycle < mrs_cycle + TMOD)
          violate("tMOD", mrs_cycle + TMOD, "ZQ");
        if (violations == v_before) begin
          busy_until = cycle + TZQINIT;
          busy_name = "tZQINIT";
          last_cmd = cycle;
          phase = 4;
          zq_seen = 1;
        end
      end else if (op == 5) begin
        if (phase_now != 4 || !zq_seen)
          violate("init_order", cycle, "ACT v_before ZQ completion");
        if (last_cmd > -1000 && cycle < last_cmd + gap)
          violate("tPPD", last_cmd + gap, "ACT");
        if (last_act_any > -1000 && cycle < last_act_any + TRRD)
          violate("tRRD", last_act_any + TRRD, "ACT");
        if (row_open[bank])
          violate("require_idle_bank", cycle, $sformatf("bank %0d", bank));
        if (pre_at[bank] > -1000 && cycle < pre_at[bank] + TRP)
          violate("tRP", pre_at[bank] + TRP, $sformatf("bank %0d", bank));
        if (act_at[bank] > -1000 && cycle < act_at[bank] + TRC)
          violate("tRC", act_at[bank] + TRC, $sformatf("bank %0d", bank));
        if (violations == v_before) begin
          row_open[bank] = 1;
          act_at[bank] = cycle;
          last_act_any = cycle;
          last_cmd = cycle;
          rd_at[bank] = -100000;
          wr_at[bank] = -100000;
          phase = 4;
        end
      end else if ((op == 0 || op == 1) && !rejected) begin
        clocks = (((rise >> 5) & 63) + 1) * 8;
        if (phase_now != 4 || !zq_seen)
          violate("init_order", cycle, "CAS v_before ZQ completion");
        if (last_cmd > -1000 && cycle < last_cmd + gap)
          violate("tPPD", last_cmd + gap, op == 0 ? "RD" : "WR");
        if (!row_open[bank])
          violate("row_open", cycle, $sformatf("bank %0d", bank));
        else if (cycle < act_at[bank] + TRCD)
          violate("tRCD", act_at[bank] + TRCD, $sformatf("bank %0d", bank));
        if (col_kind != 0 && cycle < col_at + col_ck)
          violate("tCCD", col_at + col_ck, "previous burst");
        if (turn != 0 && col_kind == 2 && op == 0 && cycle < col_at + turn)
          violate("tWTR", col_at + turn, "write to read");
        if (turn != 0 && col_kind == 1 && op == 1 && cycle < col_at + turn)
          violate("tRTW", col_at + turn, "read to write");
        if (violations == v_before) begin
          col_at = cycle;
          col_ck = clocks;
          col_kind = (op == 0) ? 1 : 2;
          last_cmd = cycle;
          if (op == 0) begin
            rd_at[bank] = cycle;
            rd_ck[bank] = clocks;
          end else begin
            wr_at[bank] = cycle;
            wr_ck[bank] = clocks;
          end
        end
      end else if (op == 6) begin
        int step, refop;
        mask = (rise >> 6) & 15;
        refop = (fall >> 1) & 3;
        nbank = popcount4(mask);
        step = (refop == 1) ? TREFI_LP : TREFI_FST;
        window = REFRESH_ROW_STEP ? (ROWS * step * nbank) : step;
        if (phase_now != 4 || !zq_seen)
          violate("init_order", cycle, "REF v_before ZQ completion");
        if (refop > 1) violate("REFOP_reserved", cycle, "reserved refresh mode");
        if (nbank == 0) violate("REF_bank_mask", cycle, "no selected bank");
        if (CASE_TEMP_GT85 && refop == 1 && nbank > 2)
          violate("REF_LP_high_temp", cycle, "LP REF above 85C selects more than two banks");
        if (last_cmd > -1000 && cycle < last_cmd + gap)
          violate("tPPD", last_cmd + gap, "REF");
        for (int b = 0; b < 4; b++) begin
          if (act_at[b] > -1000 && cycle < act_at[b] + TRC)
            violate("tRC", act_at[b] + TRC, $sformatf("bank %0d ACT to REF", b));
          if (!row_open[b] && pre_at[b] > -1000 && cycle < pre_at[b] + TRP)
            violate("tRP", pre_at[b] + TRP, $sformatf("bank %0d PRE to REF", b));
          if (row_open[b]) begin
            if (rd_at[b] > -1000 && cycle < rd_at[b] + rl + rd_ck[b])
              violate("read_to_precharge", rd_at[b] + rl + rd_ck[b],
                $sformatf("bank %0d READ to REF", b));
            if (wr_at[b] > -1000 && cycle <
                wr_at[b] + rl + wr_ck[b] + ((nwr > TWR) ? nwr : TWR))
              violate("tWR", wr_at[b] + rl + wr_ck[b] +
                ((nwr > TWR) ? nwr : TWR), $sformatf("bank %0d WRITE to REF", b));
          end
        end
        if (violations == v_before) begin
          for (int b = 0; b < 4; b++) begin
            row_open[b] = 0;
            pre_at[b] = cycle;
          end
          busy_until = cycle + window;
          refreshes = refreshes + 1;
          busy_name = "tREFI";
          last_cmd = cycle;
          col_kind = 0;
          phase = 4;
          $display("RPC_REFRESH cycle=%0d mask=%0h banks=%0d window=%0d row_step=%0d",
            cycle, mask, nbank, window, REFRESH_ROW_STEP);
        end
      end else begin
        violate("unsupported_packet", cycle, "command not implemented in observer");
      end
    end
  end
endmodule
