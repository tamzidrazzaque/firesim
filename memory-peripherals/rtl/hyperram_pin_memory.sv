`timescale 1ns/1ps

// S80KS2562 Rev. *C digital HyperBus device for controller verification.
// The host and device use separate DQ/RWDS value and output-enable signals;
// a pad wrapper may connect them to inouts. Samples CA and writes on both CK
// edges and presents reads on both edges. Analog setup/hold and VCC ramp are
// outside this digital model. force_refresh_collision_i fixes the otherwise
// unpublished internal refresh phase for a directed variable-latency test.
module hyperram_pin_memory #(
  parameter int TCK_NS = 5,
  parameter int TCSHI_NS = 6,
  parameter int TRWR_NS = 35,
  parameter int TRP_NS = 200,
  parameter int TRH_NS = 200,
  parameter int TCSM_NS = 4000, // use 1000 for TA > 85 C
  parameter int TCSS_NS = 4,
  parameter bit FATAL_ON_VIOLATION = 1
) (
  input  logic       ck_i,
  input  logic       reset_ni,
  input  logic       cs_ni,
  input  logic [7:0] dq_i,
  input  logic       dq_oe_i,
  input  logic       rwds_i,
  input  logic       rwds_oe_i,
  input  logic       force_refresh_collision_i,
  output logic [7:0] dq_o,
  output logic       dq_oe_o,
  output logic       rwds_o,
  output logic       rwds_oe_o
);
  // Unwritten memory reads zero in this simulation. Data retention is not
  // modeled; the controller's refresh response is tested through RWDS.
  byte unsigned mem [int unsigned];
  logic [15:0] cr0 = 16'h8f2f;
  logic [15:0] cr1 = 16'hffc1;
  int violations = 0;
  int transactions = 0;
  int collisions = 0;
  realtime cs_fall_at, cs_rise_at, reset_low_at, reset_rise_at, last_rise_at;
  realtime cs_gap_ns;
  bit have_cs_rise = 0;
  bit have_reset_rise = 0;
  bit reset_low_seen = 1; // testbench may start with RESET# low at time zero
  bit selected = 0;
  bit ca_done = 0;
  bit tcsm_reported = 0;
  bit rise_seen = 0;
  bit read_q, reg_q, linear_q, collision_q;
  bit last_read = 0;
  logic [47:0] ca;
  int rise_count = 0;
  int data_start_ck = 0;
  int data_bytes = 0;
  int unsigned word_addr = 0;
  byte unsigned reg_hi;

  task automatic bad(input string rule);
    violations = violations + 1;
    $display("HYPER_TIMING_VIOLATION rule=%s time=%0t txn=%0d", rule, $time, transactions);
    if (FATAL_ON_VIOLATION) $fatal(1, "HyperRAM %s", rule);
  endtask

  function automatic int base_latency(input logic [15:0] cfg);
    case (cfg[7:4])
      4'h0: return 5;
      4'h1: return 6;
      4'h2: return 7;
      4'he: return 3;
      4'hf: return 4;
      default: return -1;
    endcase
  endfunction

  function automatic int wrap_words(input logic [15:0] cfg);
    case (cfg[1:0])
      2'b00: return 64;
      2'b01: return 32;
      2'b10: return 8;
      default: return 16;
    endcase
  endfunction

  function automatic int unsigned data_word(input int unsigned n);
    int unsigned w, mask, base, offset;
    w = word_addr;
    if (!linear_q) begin
      mask = wrap_words(cr0) - 1;
      base = word_addr & ~mask;
      offset = word_addr & mask;
      if (!cr0[2] && n >= wrap_words(cr0))
        w = base + wrap_words(cr0) + n - wrap_words(cr0);
      else
        w = base + ((offset + n) & mask);
    end else w = word_addr + n;
    return w & 32'h00ffffff; // 256 Mb = 16 M 16-bit words
  endfunction

  function automatic byte unsigned read_byte(input int unsigned n);
    int unsigned a;
    logic [15:0] v;
    if (reg_q) begin
      case (word_addr)
        0: v = 16'h0e86; // ID0, section 6.2.1
        1: v = 16'h0001; // ID1, section 6.2
        'h800: v = cr0;
        'h801: v = cr1;
        default: v = 0;
      endcase
      return n[0] ? v[7:0] : v[15:8];
    end
    a = (data_word(n / 2) << 1) | (n & 1);
    return (mem.exists(a) != 0) ? mem[a] : 8'h00;
  endfunction

  initial begin
    cs_fall_at = 0;
    cs_rise_at = 0;
    reset_low_at = 0;
    reset_rise_at = 0;
    dq_o = 0;
    dq_oe_o = 0;
    rwds_o = 0;
    rwds_oe_o = 0;
  end

  always @(negedge reset_ni) begin
    reset_low_seen = 1;
    reset_low_at = $realtime;
    have_reset_rise = 0;
    selected = 0;
    dq_oe_o = 0;
    rwds_oe_o = 0;
  end

  always @(posedge reset_ni) begin
    if (reset_low_seen && $realtime - reset_low_at < TRP_NS)
      bad("tRP_reset_low");
    reset_rise_at = $realtime;
    have_reset_rise = 1;
    cr0 = 16'h8f2f;
    cr1 = 16'hffc1;
  end

  always @(negedge cs_ni) begin
    if (!reset_ni || !have_reset_rise || $realtime - reset_rise_at < TRH_NS)
      bad("tRH_reset_to_CS");
    if (!cr0[15]) bad("deep_power_down_requires_reset");
    if (ck_i !== 1'b0) bad("CS_assert_when_CK_high");
    if (have_cs_rise && $realtime - cs_rise_at < TCSHI_NS)
      bad("tCSHI");
    cs_gap_ns = have_cs_rise ? $realtime - cs_rise_at : 1.0e12;
    cs_fall_at = $realtime;
    selected = 1;
    ca_done = 0;
    tcsm_reported = 0;
    rise_count = 0;
    rise_seen = 0;
    data_bytes = 0;
    ca = 0;
    collision_q = force_refresh_collision_i || cr0[3];
    if (force_refresh_collision_i) collisions = collisions + 1;
    dq_oe_o = 0;
    rwds_o = collision_q;
    rwds_oe_o = 1; // device owns RWDS throughout CA
    transactions = transactions + 1;
  end

  always @(posedge cs_ni) begin
    if (selected) begin
      if (ck_i !== 1'b0) bad("CS_release_when_CK_high");
      if (!tcsm_reported && $realtime - cs_fall_at > TCSM_NS) bad("tCSM");
      if (!ca_done) bad("short_CA");
      else if (reg_q && !read_q && data_bytes != 2) bad("register_write_length");
      else if (!reg_q && data_bytes[0]) bad("partial_word");
      cs_rise_at = $realtime;
      have_cs_rise = 1;
      last_read = read_q;
      selected = 0;
      dq_oe_o = 0;
      rwds_oe_o = 0;
    end
  end

  // Simulation outputs settle after each CK edge. Sample them after a delta
  // cycle in a testbench; this is a digital protocol model, not an AC pad model.
  always @(posedge ck_i or negedge ck_i) begin : edge_transfer
    int ck, half, byte_no, lat;
    logic [47:0] next_ca;
    logic [15:0] new_reg;
    int unsigned a;
    if (selected && reset_ni) begin
      if (!tcsm_reported && $realtime - cs_fall_at > TCSM_NS) begin
        bad("tCSM");
        tcsm_reported = 1;
      end
      half = ck_i ? 0 : 1;
      ck = ck_i ? rise_count : rise_count - 1;
      if (ck_i) begin
        if (!rise_seen && $realtime - cs_fall_at < TCSS_NS) bad("tCSS");
        if (rise_seen && $realtime - last_rise_at < TCK_NS) bad("tCK");
        last_rise_at = $realtime;
        rise_seen = 1;
        rise_count = rise_count + 1;
      end
      if (ck < 3) begin
        if (!dq_oe_i) bad("CA_DQ_not_driven");
        if (rwds_oe_i) bad("CA_RWDS_contention");
        next_ca = ca;
        next_ca[47 - (2*ck+half)*8 -: 8] = dq_i;
        ca = next_ca;
        if (ck == 2 && half == 1) begin
          ca_done = 1;
          read_q = next_ca[47];
          reg_q = next_ca[46];
          linear_q = next_ca[45];
          word_addr = (int'(next_ca[44:16]) << 3) | int'(next_ca[2:0]);
          if (next_ca[44:37] != 0 && !reg_q) bad("address_above_256Mb");
          if (last_read && !read_q && cs_gap_ns < TRWR_NS)
            bad("tRWR");
          if (reg_q && !read_q && !linear_q) bad("register_write_must_be_linear");
          lat = base_latency(cr0);
          if (lat < 0) begin
            bad("reserved_latency_code");
            lat = 7;
          end
          data_start_ck = 3 + ((reg_q && !read_q) ? 0 : lat * (collision_q ? 2 : 1));
          // Read latency drives RWDS low; write latency releases it.
          rwds_oe_o = read_q;
          rwds_o = 0;
        end
      end else if (ca_done && ck >= data_start_ck) begin
        byte_no = 2 * (ck - data_start_ck) + half;
        if (read_q) begin
          if (dq_oe_i) bad("read_DQ_contention");
          dq_o = read_byte(byte_no);
          dq_oe_o = 1;
          rwds_o = ck_i;
          rwds_oe_o = 1;
          data_bytes = data_bytes + 1;
        end else begin
          if (!dq_oe_i) bad("write_DQ_not_driven");
          if (reg_q) begin
            if (rwds_oe_i) bad("register_RWDS_contention");
            if (byte_no == 0) reg_hi = dq_i;
            else if (byte_no == 1) begin
              new_reg = {reg_hi, dq_i};
              case (word_addr)
                'h800: begin
                  if (new_reg[11:8] != 4'hf || base_latency(new_reg) < 0)
                    bad("CR0_reserved_encoding");
                  else cr0 = new_reg;
                end
                'h801: begin
                  if (new_reg[15:7] != 9'h1ff)
                    bad("CR1_reserved_encoding");
                  else if (new_reg[1:0] != cr1[1:0])
                    bad("CR1_read_only_DRI");
                  else if (new_reg[5])
                    bad("hybrid_sleep_not_modeled");
                  else cr1 = new_reg;
                end
                0, 1: bad("write_read_only_ID");
                default: bad("undefined_register");
              endcase
            end else bad("register_write_length");
          end else begin
            if (!rwds_oe_i) bad("write_RWDS_not_driven");
            if (!rwds_i) begin
              a = (data_word(byte_no / 2) << 1) | (byte_no & 1);
              mem[a] = dq_i;
            end
          end
          data_bytes = data_bytes + 1;
        end
      end else if (ca_done) begin
        if (dq_oe_i) bad("latency_DQ_contention");
        if (rwds_oe_i) bad("latency_RWDS_contention");
      end
    end
  end
endmodule
