module RpcTimingChecker(
  input         clock,
  input         reset,
  input         io_valid, // @[src/main/scala/rpc/RpcTimingChecker.scala 41:14]
  input  [63:0] io_cycle, // @[src/main/scala/rpc/RpcTimingChecker.scala 41:14]
  input  [31:0] io_packet, // @[src/main/scala/rpc/RpcTimingChecker.scala 41:14]
  input  [15:0] io_tckPs, // @[src/main/scala/rpc/RpcTimingChecker.scala 41:14]
  input  [1:0]  io_refreshSelect, // @[src/main/scala/rpc/RpcTimingChecker.scala 41:14]
  output        io_accepted, // @[src/main/scala/rpc/RpcTimingChecker.scala 41:14]
  output [1:0]  io_kind, // @[src/main/scala/rpc/RpcTimingChecker.scala 41:14]
  output [7:0]  io_constraintId, // @[src/main/scala/rpc/RpcTimingChecker.scala 41:14]
  output [63:0] io_earliest, // @[src/main/scala/rpc/RpcTimingChecker.scala 41:14]
  output [3:0]  io_opCode, // @[src/main/scala/rpc/RpcTimingChecker.scala 41:14]
  output [63:0] io_earliestRs1, // @[src/main/scala/rpc/RpcTimingChecker.scala 41:14]
  output [63:0] io_earliestRs2, // @[src/main/scala/rpc/RpcTimingChecker.scala 41:14]
  output [1:0]  io_bank, // @[src/main/scala/rpc/RpcTimingChecker.scala 41:14]
  output [11:0] io_row, // @[src/main/scala/rpc/RpcTimingChecker.scala 41:14]
  output [5:0]  io_column, // @[src/main/scala/rpc/RpcTimingChecker.scala 41:14]
  output [6:0]  io_words, // @[src/main/scala/rpc/RpcTimingChecker.scala 41:14]
  output [4:0]  io_latency // @[src/main/scala/rpc/RpcTimingChecker.scala 41:14]
);
`ifdef RANDOMIZE_REG_INIT
  reg [31:0] _RAND_0;
  reg [63:0] _RAND_1;
  reg [31:0] _RAND_2;
  reg [31:0] _RAND_3;
  reg [31:0] _RAND_4;
  reg [31:0] _RAND_5;
  reg [63:0] _RAND_6;
  reg [31:0] _RAND_7;
  reg [31:0] _RAND_8;
  reg [31:0] _RAND_9;
  reg [31:0] _RAND_10;
  reg [31:0] _RAND_11;
  reg [31:0] _RAND_12;
  reg [31:0] _RAND_13;
  reg [31:0] _RAND_14;
  reg [31:0] _RAND_15;
  reg [31:0] _RAND_16;
  reg [31:0] _RAND_17;
  reg [31:0] _RAND_18;
  reg [31:0] _RAND_19;
  reg [31:0] _RAND_20;
  reg [31:0] _RAND_21;
  reg [31:0] _RAND_22;
  reg [63:0] _RAND_23;
  reg [63:0] _RAND_24;
  reg [63:0] _RAND_25;
  reg [63:0] _RAND_26;
  reg [31:0] _RAND_27;
  reg [31:0] _RAND_28;
  reg [31:0] _RAND_29;
  reg [31:0] _RAND_30;
  reg [63:0] _RAND_31;
  reg [63:0] _RAND_32;
  reg [63:0] _RAND_33;
  reg [63:0] _RAND_34;
  reg [31:0] _RAND_35;
  reg [31:0] _RAND_36;
  reg [31:0] _RAND_37;
  reg [31:0] _RAND_38;
  reg [63:0] _RAND_39;
  reg [63:0] _RAND_40;
  reg [63:0] _RAND_41;
  reg [63:0] _RAND_42;
  reg [31:0] _RAND_43;
  reg [63:0] _RAND_44;
  reg [31:0] _RAND_45;
  reg [31:0] _RAND_46;
  reg [63:0] _RAND_47;
  reg [31:0] _RAND_48;
  reg [31:0] _RAND_49;
  reg [63:0] _RAND_50;
  reg [31:0] _RAND_51;
  reg [31:0] _RAND_52;
  reg [31:0] _RAND_53;
  reg [31:0] _RAND_54;
  reg [31:0] _RAND_55;
  reg [63:0] _RAND_56;
  reg [31:0] _RAND_57;
  reg [31:0] _RAND_58;
  reg [63:0] _RAND_59;
  reg [31:0] _RAND_60;
  reg [31:0] _RAND_61;
  reg [31:0] _RAND_62;
`endif // RANDOMIZE_REG_INIT
  wire [15:0] tck = io_tckPs == 16'h0 ? 16'h1 : io_tckPs; // @[src/main/scala/rpc/RpcTimingChecker.scala 49:24]
  wire [15:0] rise = io_packet[15:0]; // @[src/main/scala/rpc/RpcTimingChecker.scala 58:31]
  wire [15:0] fall = io_packet[31:16]; // @[src/main/scala/rpc/RpcTimingChecker.scala 59:31]
  wire  f0 = fall[0]; // @[src/main/scala/rpc/RpcTimingChecker.scala 61:24]
  wire [1:0] f21 = fall[2:1]; // @[src/main/scala/rpc/RpcTimingChecker.scala 62:25]
  wire [3:0] _op_T = f0 ? 4'ha : 4'h3; // @[src/main/scala/rpc/RpcTimingChecker.scala 64:24]
  wire [3:0] _op_T_1 = f0 ? 4'h9 : 4'h4; // @[src/main/scala/rpc/RpcTimingChecker.scala 65:24]
  wire [3:0] _op_T_5 = f21 == 2'h2 ? 4'h8 : 4'hf; // @[src/main/scala/rpc/RpcTimingChecker.scala 67:67]
  wire [3:0] _op_T_6 = f21 == 2'h0 ? 4'h7 : _op_T_5; // @[src/main/scala/rpc/RpcTimingChecker.scala 67:35]
  wire [3:0] _op_T_7 = ~f0 ? 4'h1 : _op_T_6; // @[src/main/scala/rpc/RpcTimingChecker.scala 67:16]
  wire [3:0] _op_T_8 = f0 ? 4'hf : 4'h5; // @[src/main/scala/rpc/RpcTimingChecker.scala 69:24]
  wire [3:0] _op_T_9 = f0 ? 4'hf : 4'h2; // @[src/main/scala/rpc/RpcTimingChecker.scala 70:24]
  wire [3:0] _op_T_10 = f0 ? 4'hf : 4'h6; // @[src/main/scala/rpc/RpcTimingChecker.scala 71:24]
  wire [3:0] _op_T_11 = f0 ? 4'hf : 4'hb; // @[src/main/scala/rpc/RpcTimingChecker.scala 72:24]
  wire [3:0] _GEN_0 = 3'h7 == rise[2:0] ? _op_T_11 : 4'hf; // @[src/main/scala/rpc/RpcTimingChecker.scala 63:22 72:18 60:31]
  wire [3:0] _GEN_1 = 3'h6 == rise[2:0] ? _op_T_10 : _GEN_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 63:22 71:18]
  wire [3:0] _GEN_2 = 3'h5 == rise[2:0] ? _op_T_9 : _GEN_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 63:22 70:18]
  wire [3:0] _GEN_3 = 3'h4 == rise[2:0] ? _op_T_8 : _GEN_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 63:22 69:18]
  wire [3:0] _GEN_4 = 3'h2 == rise[2:0] ? _op_T_7 : _GEN_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 63:22 67:10]
  wire [3:0] _GEN_5 = 3'h1 == rise[2:0] ? _op_T_1 : _GEN_4; // @[src/main/scala/rpc/RpcTimingChecker.scala 63:22 65:18]
  wire [3:0] op = 3'h0 == rise[2:0] ? _op_T : _GEN_5; // @[src/main/scala/rpc/RpcTimingChecker.scala 63:22 64:18]
  wire  isMrs = op == 4'h1; // @[src/main/scala/rpc/RpcTimingChecker.scala 74:39]
  wire  isAct = op == 4'h2; // @[src/main/scala/rpc/RpcTimingChecker.scala 74:39]
  wire  isRd = op == 4'h3; // @[src/main/scala/rpc/RpcTimingChecker.scala 74:39]
  wire  isWr = op == 4'h4; // @[src/main/scala/rpc/RpcTimingChecker.scala 74:39]
  wire  isPre = op == 4'h5; // @[src/main/scala/rpc/RpcTimingChecker.scala 74:39]
  wire  isRef = op == 4'h6; // @[src/main/scala/rpc/RpcTimingChecker.scala 74:39]
  wire  isZq = op == 4'h9; // @[src/main/scala/rpc/RpcTimingChecker.scala 74:39]
  wire  isReset = op == 4'ha; // @[src/main/scala/rpc/RpcTimingChecker.scala 74:39]
  wire  isUtr = op == 4'hb; // @[src/main/scala/rpc/RpcTimingChecker.scala 74:39]
  wire  _isPd_T = op == 4'h7; // @[src/main/scala/rpc/RpcTimingChecker.scala 74:39]
  wire  _isPd_T_1 = op == 4'h8; // @[src/main/scala/rpc/RpcTimingChecker.scala 74:39]
  wire  isPd = _isPd_T | _isPd_T_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 84:40]
  wire  isUndef = op == 4'hf; // @[src/main/scala/rpc/RpcTimingChecker.scala 74:39]
  wire [1:0] ba = rise[4:3]; // @[src/main/scala/rpc/RpcTimingChecker.scala 87:24]
  wire [11:0] actRow = fall[12:1]; // @[src/main/scala/rpc/RpcTimingChecker.scala 88:28]
  wire [6:0] words = rise[10:5] + 6'h1; // @[src/main/scala/rpc/RpcTimingChecker.scala 90:35]
  wire [3:0] bankMask = rise[9:6]; // @[src/main/scala/rpc/RpcTimingChecker.scala 91:30]
  wire [1:0] zqop = rise[15:14]; // @[src/main/scala/rpc/RpcTimingChecker.scala 93:26]
  wire  utrEn = rise[3]; // @[src/main/scala/rpc/RpcTimingChecker.scala 94:27]
  wire [3:0] mZout = rise[12:9]; // @[src/main/scala/rpc/RpcTimingChecker.scala 97:27]
  wire [2:0] mCl = rise[5:3]; // @[src/main/scala/rpc/RpcTimingChecker.scala 99:25]
  wire  mFixed = fall[15]; // @[src/main/scala/rpc/RpcTimingChecker.scala 100:28]
  wire  mCsrfx = fall[13]; // @[src/main/scala/rpc/RpcTimingChecker.scala 102:28]
  reg  everReset; // @[src/main/scala/rpc/RpcTimingChecker.scala 120:34]
  reg [63:0] resetAt; // @[src/main/scala/rpc/RpcTimingChecker.scala 121:32]
  reg  needPrea; // @[src/main/scala/rpc/RpcTimingChecker.scala 122:33]
  reg  needMrs; // @[src/main/scala/rpc/RpcTimingChecker.scala 123:32]
  reg  needZqInit; // @[src/main/scala/rpc/RpcTimingChecker.scala 124:35]
  reg  havePrev; // @[src/main/scala/rpc/RpcTimingChecker.scala 126:33]
  reg [63:0] prevAt; // @[src/main/scala/rpc/RpcTimingChecker.scala 127:31]
  reg  bankOpen_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  bankOpen_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  bankOpen_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  bankOpen_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  bankKnown_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  bankKnown_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  bankKnown_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  bankKnown_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg [11:0] openRow_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg [11:0] openRow_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg [11:0] openRow_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg [11:0] openRow_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  actValid_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  actValid_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  actValid_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  actValid_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg [63:0] actAt_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg [63:0] actAt_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg [63:0] actAt_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg [63:0] actAt_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  preValid_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  preValid_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  preValid_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  preValid_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg [63:0] preAt_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg [63:0] preAt_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg [63:0] preAt_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg [63:0] preAt_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  wrValid_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  wrValid_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  wrValid_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  wrValid_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg [63:0] wrEndAt_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg [63:0] wrEndAt_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg [63:0] wrEndAt_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg [63:0] wrEndAt_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
  reg  actAnyValid; // @[src/main/scala/rpc/RpcTimingChecker.scala 138:36]
  reg [63:0] actAnyAt; // @[src/main/scala/rpc/RpcTimingChecker.scala 139:33]
  reg  burstValid; // @[src/main/scala/rpc/RpcTimingChecker.scala 141:35]
  reg  burstWrite; // @[src/main/scala/rpc/RpcTimingChecker.scala 142:35]
  reg [63:0] burstEnd; // @[src/main/scala/rpc/RpcTimingChecker.scala 143:33]
  reg  modeValid; // @[src/main/scala/rpc/RpcTimingChecker.scala 145:34]
  reg  modeWasMrs; // @[src/main/scala/rpc/RpcTimingChecker.scala 146:35]
  reg [63:0] modeAt; // @[src/main/scala/rpc/RpcTimingChecker.scala 147:31]
  reg [2:0] mrCl; // @[src/main/scala/rpc/RpcTimingChecker.scala 150:29]
  reg [3:0] mrZout; // @[src/main/scala/rpc/RpcTimingChecker.scala 152:31]
  reg  mrCsrfx; // @[src/main/scala/rpc/RpcTimingChecker.scala 155:32]
  reg  utrMode; // @[src/main/scala/rpc/RpcTimingChecker.scala 158:32]
  reg  zqValid; // @[src/main/scala/rpc/RpcTimingChecker.scala 161:32]
  reg [63:0] zqAt; // @[src/main/scala/rpc/RpcTimingChecker.scala 162:29]
  reg [1:0] zqOpR; // @[src/main/scala/rpc/RpcTimingChecker.scala 163:30]
  reg  refPending; // @[src/main/scala/rpc/RpcTimingChecker.scala 165:35]
  reg [63:0] refAt; // @[src/main/scala/rpc/RpcTimingChecker.scala 166:30]
  reg [2:0] refBanks; // @[src/main/scala/rpc/RpcTimingChecker.scala 167:33]
  reg  refLp; // @[src/main/scala/rpc/RpcTimingChecker.scala 168:30]
  reg  refLoop; // @[src/main/scala/rpc/RpcTimingChecker.scala 169:32]
  wire [15:0] _cRCD_T_1 = tck - 16'h1; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:49]
  wire [16:0] _cRCD_T_2 = 16'h35b6 + _cRCD_T_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:41]
  wire [16:0] cRCD = _cRCD_T_2 / tck; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:57]
  wire [16:0] _cRC_T_2 = 16'hbe6e + _cRCD_T_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:41]
  wire [16:0] cRC = _cRC_T_2 / tck; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:57]
  wire [16:0] _cRAS_T_2 = 16'h88b8 + _cRCD_T_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:41]
  wire [16:0] cRAS = _cRAS_T_2 / tck; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:57]
  wire [16:0] _cRRD_T_2 = 16'h1d4c + _cRCD_T_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:41]
  wire [16:0] cRRD = _cRRD_T_2 / tck; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:57]
  wire [16:0] _cWR_T_2 = 16'h3a98 + _cRCD_T_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:41]
  wire [16:0] cWR = _cWR_T_2 / tck; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:57]
  wire [22:0] _GEN_277 = {{7'd0}, _cRCD_T_1}; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:41]
  wire [23:0] _cRESET_T_2 = 23'h4c4b40 + _GEN_277; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:41]
  wire [23:0] cRESET = _cRESET_T_2 / tck; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:57]
  wire [16:0] cMOD = 17'hc > cWR ? 17'hc : cWR; // @[src/main/scala/rpc/RpcTimingChecker.scala 52:49]
  wire [27:0] _GEN_278 = {{12'd0}, _cRCD_T_1}; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:41]
  wire [28:0] _cClockStable_T_2 = 28'hbebc200 + _GEN_278; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:41]
  wire [28:0] cClockStable = _cClockStable_T_2 / tck; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:57]
  wire [20:0] _GEN_279 = {{5'd0}, _cRCD_T_1}; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:41]
  wire [21:0] _zqCycles_T_2 = 21'h1e8480 + _GEN_279; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:41]
  wire [21:0] _zqCycles_T_3 = _zqCycles_T_2 / tck; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:57]
  wire [18:0] _GEN_280 = {{3'd0}, _cRCD_T_1}; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:41]
  wire [19:0] _zqCycles_T_6 = 19'h57e40 + _GEN_280; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:41]
  wire [19:0] _zqCycles_T_7 = _zqCycles_T_6 / tck; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:57]
  wire [16:0] _GEN_281 = {{1'd0}, _cRCD_T_1}; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:41]
  wire [17:0] _zqCycles_T_10 = 17'h15f90 + _GEN_281; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:41]
  wire [17:0] _zqCycles_T_11 = _zqCycles_T_10 / tck; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:57]
  wire [16:0] _zqCycles_T_14 = 16'hc350 + _cRCD_T_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:41]
  wire [16:0] _zqCycles_T_15 = _zqCycles_T_14 / tck; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:57]
  wire [21:0] refiPs = refLp ? 22'h30d400 : 22'h186a0; // @[src/main/scala/rpc/RpcTimingChecker.scala 190:27]
  wire [23:0] _refOverheadPs_T = refiPs * 2'h3; // @[src/main/scala/rpc/RpcTimingChecker.scala 192:12]
  wire [24:0] _refOverheadPs_T_1 = _refOverheadPs_T + 24'h1388; // @[src/main/scala/rpc/RpcTimingChecker.scala 192:34]
  wire [13:0] _refOverheadPs_T_2 = refLoop ? 14'h2ee0 : 14'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 192:56]
  wire [24:0] _GEN_282 = {{11'd0}, _refOverheadPs_T_2}; // @[src/main/scala/rpc/RpcTimingChecker.scala 192:50]
  wire [25:0] refOverheadPs = _refOverheadPs_T_1 + _GEN_282; // @[src/main/scala/rpc/RpcTimingChecker.scala 192:50]
  wire [15:0] _refDone1_T = refBanks * 13'h1000; // @[src/main/scala/rpc/RpcTimingChecker.scala 193:84]
  wire [37:0] _refDone1_T_1 = _refDone1_T * refiPs; // @[src/main/scala/rpc/RpcTimingChecker.scala 193:96]
  wire [37:0] _GEN_283 = {{12'd0}, refOverheadPs}; // @[src/main/scala/rpc/RpcTimingChecker.scala 193:72]
  wire [38:0] _refDone1_T_2 = _GEN_283 + _refDone1_T_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 193:72]
  wire [38:0] _GEN_284 = {{23'd0}, _cRCD_T_1}; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:41]
  wire [39:0] _refDone1_T_5 = _refDone1_T_2 + _GEN_284; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:41]
  wire [39:0] _refDone1_T_6 = _refDone1_T_5 / tck; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:57]
  wire [63:0] _GEN_285 = {{24'd0}, _refDone1_T_6}; // @[src/main/scala/rpc/RpcTimingChecker.scala 193:52]
  wire [63:0] refDone1 = refAt + _GEN_285; // @[src/main/scala/rpc/RpcTimingChecker.scala 193:52]
  wire [15:0] _refDone2_T = refBanks * 13'h1388; // @[src/main/scala/rpc/RpcTimingChecker.scala 193:84]
  wire [37:0] _refDone2_T_1 = _refDone2_T * refiPs; // @[src/main/scala/rpc/RpcTimingChecker.scala 193:96]
  wire [38:0] _refDone2_T_2 = _GEN_283 + _refDone2_T_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 193:72]
  wire [39:0] _refDone2_T_5 = _refDone2_T_2 + _GEN_284; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:41]
  wire [39:0] _refDone2_T_6 = _refDone2_T_5 / tck; // @[src/main/scala/rpc/RpcTimingChecker.scala 50:57]
  wire [63:0] _GEN_288 = {{24'd0}, _refDone2_T_6}; // @[src/main/scala/rpc/RpcTimingChecker.scala 193:52]
  wire [63:0] refDone2 = refAt + _GEN_288; // @[src/main/scala/rpc/RpcTimingChecker.scala 193:52]
  wire  _T_8 = ~everReset; // @[src/main/scala/rpc/RpcTimingChecker.scala 210:12]
  wire  _T_9 = ~everReset & isReset; // @[src/main/scala/rpc/RpcTimingChecker.scala 210:23]
  wire [63:0] _GEN_289 = {{35'd0}, cClockStable}; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:32]
  wire  take = _T_9 & _GEN_289 > 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_10 = take ? {{35'd0}, cClockStable} : 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_11 = take ? 8'ha : 8'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire [63:0] _GEN_290 = {{40'd0}, cRESET}; // @[src/main/scala/rpc/RpcTimingChecker.scala 211:31]
  wire [63:0] _T_13 = resetAt + _GEN_290; // @[src/main/scala/rpc/RpcTimingChecker.scala 211:31]
  wire  take_1 = everReset & _T_13 > _T_10; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_14 = take_1 ? _T_13 : _T_10; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_15 = take_1 ? 8'hc : _T_11; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_17 = burstValid & ~burstWrite; // @[src/main/scala/rpc/RpcTimingChecker.scala 212:23]
  wire [63:0] _T_19 = burstEnd + 64'hb; // @[src/main/scala/rpc/RpcTimingChecker.scala 212:48]
  wire  take_2 = _T_17 & _T_19 > _T_14; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_20 = take_2 ? _T_19 : _T_14; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_21 = take_2 ? 8'h16 : _T_15; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_22 = burstValid & burstWrite; // @[src/main/scala/rpc/RpcTimingChecker.scala 213:23]
  wire [63:0] _T_24 = burstEnd + 64'hd; // @[src/main/scala/rpc/RpcTimingChecker.scala 213:47]
  wire  take_3 = _T_22 & _T_24 > _T_20; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_25 = take_3 ? _T_24 : _T_20; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_26 = take_3 ? 8'h17 : _T_21; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire [21:0] _zqCycles_WIRE_1 = {{2'd0}, _zqCycles_T_7}; // @[src/main/scala/rpc/RpcTimingChecker.scala 182:{12,12}]
  wire [21:0] _GEN_8 = 2'h1 == zqOpR ? _zqCycles_WIRE_1 : _zqCycles_T_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 214:{26,26}]
  wire [21:0] _zqCycles_WIRE_2 = {{4'd0}, _zqCycles_T_11}; // @[src/main/scala/rpc/RpcTimingChecker.scala 182:{12,12}]
  wire [21:0] _GEN_9 = 2'h2 == zqOpR ? _zqCycles_WIRE_2 : _GEN_8; // @[src/main/scala/rpc/RpcTimingChecker.scala 214:{26,26}]
  wire [21:0] _zqCycles_WIRE_3 = {{5'd0}, _zqCycles_T_15}; // @[src/main/scala/rpc/RpcTimingChecker.scala 182:{12,12}]
  wire [21:0] _GEN_10 = 2'h3 == zqOpR ? _zqCycles_WIRE_3 : _GEN_9; // @[src/main/scala/rpc/RpcTimingChecker.scala 214:{26,26}]
  wire [63:0] _GEN_291 = {{42'd0}, _GEN_10}; // @[src/main/scala/rpc/RpcTimingChecker.scala 214:26]
  wire [63:0] _T_28 = zqAt + _GEN_291; // @[src/main/scala/rpc/RpcTimingChecker.scala 214:26]
  wire  take_4 = zqValid & _T_28 > _T_25; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_29 = take_4 ? _T_28 : _T_25; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _GEN_12 = 2'h1 == zqOpR ? 8'h1c : 8'h1b; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:{15,15}]
  wire [7:0] _GEN_13 = 2'h2 == zqOpR ? 8'h1d : _GEN_12; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:{15,15}]
  wire [7:0] _GEN_14 = 2'h3 == zqOpR ? 8'h1e : _GEN_13; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:{15,15}]
  wire [7:0] _T_30 = take_4 ? _GEN_14 : _T_26; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_32 = modeValid & isMrs & modeWasMrs; // @[src/main/scala/rpc/RpcTimingChecker.scala 215:31]
  wire [63:0] _T_34 = modeAt + 64'h4; // @[src/main/scala/rpc/RpcTimingChecker.scala 215:53]
  wire  take_5 = _T_32 & _T_34 > _T_29; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_35 = take_5 ? _T_34 : _T_29; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_36 = take_5 ? 8'h18 : _T_30; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_37 = ~isReset; // @[src/main/scala/rpc/RpcTimingChecker.scala 216:25]
  wire  _T_41 = modeValid & ~isReset & ~(isMrs & modeWasMrs); // @[src/main/scala/rpc/RpcTimingChecker.scala 216:34]
  wire [63:0] _GEN_292 = {{47'd0}, cMOD}; // @[src/main/scala/rpc/RpcTimingChecker.scala 216:68]
  wire [63:0] _T_43 = modeAt + _GEN_292; // @[src/main/scala/rpc/RpcTimingChecker.scala 216:68]
  wire  take_6 = _T_41 & _T_43 > _T_35; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_44 = take_6 ? _T_43 : _T_35; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_45 = take_6 ? 8'h19 : _T_36; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  columnAccess = isRd & ~utrMode | isWr; // @[src/main/scala/rpc/RpcTimingChecker.scala 217:49]
  wire  sel = ba == 2'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 219:18]
  wire  _T_46 = isAct & sel; // @[src/main/scala/rpc/RpcTimingChecker.scala 220:20]
  wire  _T_47 = isAct & sel & preValid_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 220:27]
  wire [63:0] _GEN_293 = {{47'd0}, cRCD}; // @[src/main/scala/rpc/RpcTimingChecker.scala 220:52]
  wire [63:0] _T_49 = preAt_0 + _GEN_293; // @[src/main/scala/rpc/RpcTimingChecker.scala 220:52]
  wire  take_7 = _T_47 & _T_49 > _T_44; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_50 = take_7 ? _T_49 : _T_44; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_51 = take_7 ? 8'h29 : _T_45; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_53 = _T_46 & actValid_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 221:27]
  wire [63:0] _GEN_294 = {{47'd0}, cRC}; // @[src/main/scala/rpc/RpcTimingChecker.scala 221:52]
  wire [63:0] _T_55 = actAt_0 + _GEN_294; // @[src/main/scala/rpc/RpcTimingChecker.scala 221:52]
  wire  take_8 = _T_53 & _T_55 > _T_50; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_56 = take_8 ? _T_55 : _T_50; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_57 = take_8 ? 8'h2a : _T_51; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_59 = columnAccess & sel & actValid_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 222:34]
  wire [63:0] _T_61 = actAt_0 + _GEN_293; // @[src/main/scala/rpc/RpcTimingChecker.scala 222:59]
  wire  take_9 = _T_59 & _T_61 > _T_56; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_62 = take_9 ? _T_61 : _T_56; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_63 = take_9 ? 8'h2c : _T_57; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_65 = isPre & bankMask[0]; // @[src/main/scala/rpc/RpcTimingChecker.scala 223:20]
  wire  _T_66 = isPre & bankMask[0] & actValid_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 223:35]
  wire [63:0] _GEN_296 = {{47'd0}, cRAS}; // @[src/main/scala/rpc/RpcTimingChecker.scala 223:60]
  wire [63:0] _T_68 = actAt_0 + _GEN_296; // @[src/main/scala/rpc/RpcTimingChecker.scala 223:60]
  wire  take_10 = _T_66 & _T_68 > _T_62; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_69 = take_10 ? _T_68 : _T_62; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_70 = take_10 ? 8'h2d : _T_63; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_73 = _T_65 & wrValid_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 224:35]
  wire [63:0] _GEN_297 = {{47'd0}, cWR}; // @[src/main/scala/rpc/RpcTimingChecker.scala 224:61]
  wire [63:0] _T_75 = wrEndAt_0 + _GEN_297; // @[src/main/scala/rpc/RpcTimingChecker.scala 224:61]
  wire  take_11 = _T_73 & _T_75 > _T_69; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_76 = take_11 ? _T_75 : _T_69; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_77 = take_11 ? 8'h2e : _T_70; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_78 = isRef & actValid_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 225:20]
  wire  take_12 = _T_78 & _T_55 > _T_76; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_81 = take_12 ? _T_55 : _T_76; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_82 = take_12 ? 8'h2a : _T_77; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_85 = (isMrs | isZq | isUtr) & preValid_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 226:39]
  wire  take_13 = _T_85 & _T_49 > _T_81; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_88 = take_13 ? _T_49 : _T_81; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_89 = take_13 ? 8'h29 : _T_82; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  sel_1 = ba == 2'h1; // @[src/main/scala/rpc/RpcTimingChecker.scala 219:18]
  wire  _T_90 = isAct & sel_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 220:20]
  wire  _T_91 = isAct & sel_1 & preValid_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 220:27]
  wire [63:0] _T_93 = preAt_1 + _GEN_293; // @[src/main/scala/rpc/RpcTimingChecker.scala 220:52]
  wire  take_14 = _T_91 & _T_93 > _T_88; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_94 = take_14 ? _T_93 : _T_88; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_95 = take_14 ? 8'h29 : _T_89; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_97 = _T_90 & actValid_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 221:27]
  wire [63:0] _T_99 = actAt_1 + _GEN_294; // @[src/main/scala/rpc/RpcTimingChecker.scala 221:52]
  wire  take_15 = _T_97 & _T_99 > _T_94; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_100 = take_15 ? _T_99 : _T_94; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_101 = take_15 ? 8'h2a : _T_95; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_103 = columnAccess & sel_1 & actValid_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 222:34]
  wire [63:0] _T_105 = actAt_1 + _GEN_293; // @[src/main/scala/rpc/RpcTimingChecker.scala 222:59]
  wire  take_16 = _T_103 & _T_105 > _T_100; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_106 = take_16 ? _T_105 : _T_100; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_107 = take_16 ? 8'h2c : _T_101; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_109 = isPre & bankMask[1]; // @[src/main/scala/rpc/RpcTimingChecker.scala 223:20]
  wire  _T_110 = isPre & bankMask[1] & actValid_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 223:35]
  wire [63:0] _T_112 = actAt_1 + _GEN_296; // @[src/main/scala/rpc/RpcTimingChecker.scala 223:60]
  wire  take_17 = _T_110 & _T_112 > _T_106; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_113 = take_17 ? _T_112 : _T_106; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_114 = take_17 ? 8'h2d : _T_107; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_117 = _T_109 & wrValid_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 224:35]
  wire [63:0] _T_119 = wrEndAt_1 + _GEN_297; // @[src/main/scala/rpc/RpcTimingChecker.scala 224:61]
  wire  take_18 = _T_117 & _T_119 > _T_113; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_120 = take_18 ? _T_119 : _T_113; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_121 = take_18 ? 8'h2e : _T_114; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_122 = isRef & actValid_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 225:20]
  wire  take_19 = _T_122 & _T_99 > _T_120; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_125 = take_19 ? _T_99 : _T_120; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_126 = take_19 ? 8'h2a : _T_121; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_129 = (isMrs | isZq | isUtr) & preValid_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 226:39]
  wire  take_20 = _T_129 & _T_93 > _T_125; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_132 = take_20 ? _T_93 : _T_125; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_133 = take_20 ? 8'h29 : _T_126; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  sel_2 = ba == 2'h2; // @[src/main/scala/rpc/RpcTimingChecker.scala 219:18]
  wire  _T_134 = isAct & sel_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 220:20]
  wire  _T_135 = isAct & sel_2 & preValid_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 220:27]
  wire [63:0] _T_137 = preAt_2 + _GEN_293; // @[src/main/scala/rpc/RpcTimingChecker.scala 220:52]
  wire  take_21 = _T_135 & _T_137 > _T_132; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_138 = take_21 ? _T_137 : _T_132; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_139 = take_21 ? 8'h29 : _T_133; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_141 = _T_134 & actValid_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 221:27]
  wire [63:0] _T_143 = actAt_2 + _GEN_294; // @[src/main/scala/rpc/RpcTimingChecker.scala 221:52]
  wire  take_22 = _T_141 & _T_143 > _T_138; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_144 = take_22 ? _T_143 : _T_138; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_145 = take_22 ? 8'h2a : _T_139; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_147 = columnAccess & sel_2 & actValid_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 222:34]
  wire [63:0] _T_149 = actAt_2 + _GEN_293; // @[src/main/scala/rpc/RpcTimingChecker.scala 222:59]
  wire  take_23 = _T_147 & _T_149 > _T_144; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_150 = take_23 ? _T_149 : _T_144; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_151 = take_23 ? 8'h2c : _T_145; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_153 = isPre & bankMask[2]; // @[src/main/scala/rpc/RpcTimingChecker.scala 223:20]
  wire  _T_154 = isPre & bankMask[2] & actValid_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 223:35]
  wire [63:0] _T_156 = actAt_2 + _GEN_296; // @[src/main/scala/rpc/RpcTimingChecker.scala 223:60]
  wire  take_24 = _T_154 & _T_156 > _T_150; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_157 = take_24 ? _T_156 : _T_150; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_158 = take_24 ? 8'h2d : _T_151; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_161 = _T_153 & wrValid_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 224:35]
  wire [63:0] _T_163 = wrEndAt_2 + _GEN_297; // @[src/main/scala/rpc/RpcTimingChecker.scala 224:61]
  wire  take_25 = _T_161 & _T_163 > _T_157; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_164 = take_25 ? _T_163 : _T_157; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_165 = take_25 ? 8'h2e : _T_158; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_166 = isRef & actValid_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 225:20]
  wire  take_26 = _T_166 & _T_143 > _T_164; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_169 = take_26 ? _T_143 : _T_164; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_170 = take_26 ? 8'h2a : _T_165; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_173 = (isMrs | isZq | isUtr) & preValid_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 226:39]
  wire  take_27 = _T_173 & _T_137 > _T_169; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_176 = take_27 ? _T_137 : _T_169; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_177 = take_27 ? 8'h29 : _T_170; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  sel_3 = ba == 2'h3; // @[src/main/scala/rpc/RpcTimingChecker.scala 219:18]
  wire  _T_178 = isAct & sel_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 220:20]
  wire  _T_179 = isAct & sel_3 & preValid_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 220:27]
  wire [63:0] _T_181 = preAt_3 + _GEN_293; // @[src/main/scala/rpc/RpcTimingChecker.scala 220:52]
  wire  take_28 = _T_179 & _T_181 > _T_176; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_182 = take_28 ? _T_181 : _T_176; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_183 = take_28 ? 8'h29 : _T_177; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_185 = _T_178 & actValid_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 221:27]
  wire [63:0] _T_187 = actAt_3 + _GEN_294; // @[src/main/scala/rpc/RpcTimingChecker.scala 221:52]
  wire  take_29 = _T_185 & _T_187 > _T_182; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_188 = take_29 ? _T_187 : _T_182; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_189 = take_29 ? 8'h2a : _T_183; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_191 = columnAccess & sel_3 & actValid_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 222:34]
  wire [63:0] _T_193 = actAt_3 + _GEN_293; // @[src/main/scala/rpc/RpcTimingChecker.scala 222:59]
  wire  take_30 = _T_191 & _T_193 > _T_188; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_194 = take_30 ? _T_193 : _T_188; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_195 = take_30 ? 8'h2c : _T_189; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_197 = isPre & bankMask[3]; // @[src/main/scala/rpc/RpcTimingChecker.scala 223:20]
  wire  _T_198 = isPre & bankMask[3] & actValid_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 223:35]
  wire [63:0] _T_200 = actAt_3 + _GEN_296; // @[src/main/scala/rpc/RpcTimingChecker.scala 223:60]
  wire  take_31 = _T_198 & _T_200 > _T_194; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_201 = take_31 ? _T_200 : _T_194; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_202 = take_31 ? 8'h2d : _T_195; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_205 = _T_197 & wrValid_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 224:35]
  wire [63:0] _T_207 = wrEndAt_3 + _GEN_297; // @[src/main/scala/rpc/RpcTimingChecker.scala 224:61]
  wire  take_32 = _T_205 & _T_207 > _T_201; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_208 = take_32 ? _T_207 : _T_201; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_209 = take_32 ? 8'h2e : _T_202; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_210 = isRef & actValid_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 225:20]
  wire  take_33 = _T_210 & _T_187 > _T_208; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_213 = take_33 ? _T_187 : _T_208; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_214 = take_33 ? 8'h2a : _T_209; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_217 = (isMrs | isZq | isUtr) & preValid_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 226:39]
  wire  take_34 = _T_217 & _T_181 > _T_213; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_220 = take_34 ? _T_181 : _T_213; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_221 = take_34 ? 8'h29 : _T_214; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  _T_222 = isAct & actAnyValid; // @[src/main/scala/rpc/RpcTimingChecker.scala 228:18]
  wire [63:0] _GEN_321 = {{47'd0}, cRRD}; // @[src/main/scala/rpc/RpcTimingChecker.scala 228:43]
  wire [63:0] _T_224 = actAnyAt + _GEN_321; // @[src/main/scala/rpc/RpcTimingChecker.scala 228:43]
  wire  take_35 = _T_222 & _T_224 > _T_220; // @[src/main/scala/rpc/RpcTimingChecker.scala 202:23]
  wire [63:0] _T_225 = take_35 ? _T_224 : _T_220; // @[src/main/scala/rpc/RpcTimingChecker.scala 203:15]
  wire [7:0] _T_226 = take_35 ? 8'h2b : _T_221; // @[src/main/scala/rpc/RpcTimingChecker.scala 204:15]
  wire  take_36 = refPending & refDone1 > _T_225; // @[src/main/scala/rpc/RpcTimingChecker.scala 231:27]
  wire [63:0] bound1 = take_36 ? refDone1 : _T_225; // @[src/main/scala/rpc/RpcTimingChecker.scala 232:9]
  wire [7:0] id1 = take_36 ? 8'h1a : _T_226; // @[src/main/scala/rpc/RpcTimingChecker.scala 232:35]
  wire  take_37 = refPending & refDone2 > _T_225; // @[src/main/scala/rpc/RpcTimingChecker.scala 231:27]
  wire [63:0] bound2 = take_37 ? refDone2 : _T_225; // @[src/main/scala/rpc/RpcTimingChecker.scala 232:9]
  wire [7:0] id2 = take_37 ? 8'h1a : _T_226; // @[src/main/scala/rpc/RpcTimingChecker.scala 232:35]
  wire [3:0] _anyOpen_T = {bankOpen_3,bankOpen_2,bankOpen_1,bankOpen_0}; // @[src/main/scala/rpc/RpcTimingChecker.scala 241:34]
  wire  anyOpen = |_anyOpen_T; // @[src/main/scala/rpc/RpcTimingChecker.scala 241:41]
  wire [63:0] _idleAt_T_2 = preValid_0 ? _T_49 : 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 242:48]
  wire [63:0] _idleAt_T_5 = preValid_1 ? _T_93 : 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 242:48]
  wire [63:0] _idleAt_T_8 = preValid_2 ? _T_137 : 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 242:48]
  wire [63:0] _idleAt_T_11 = preValid_3 ? _T_181 : 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 242:48]
  wire [63:0] _idleAt_T_13 = _idleAt_T_2 > _idleAt_T_5 ? _idleAt_T_2 : _idleAt_T_5; // @[src/main/scala/rpc/RpcTimingChecker.scala 52:49]
  wire [63:0] _idleAt_T_15 = _idleAt_T_13 > _idleAt_T_8 ? _idleAt_T_13 : _idleAt_T_8; // @[src/main/scala/rpc/RpcTimingChecker.scala 52:49]
  wire [63:0] idleAt = _idleAt_T_15 > _idleAt_T_11 ? _idleAt_T_15 : _idleAt_T_11; // @[src/main/scala/rpc/RpcTimingChecker.scala 52:49]
  wire  activeAtNow = anyOpen | io_cycle < idleAt; // @[src/main/scala/rpc/RpcTimingChecker.scala 243:37]
  wire [63:0] ear1_lower = bound1 > io_cycle ? bound1 : io_cycle; // @[src/main/scala/rpc/RpcTimingChecker.scala 52:49]
  wire [63:0] _ear1_g0_T_1 = prevAt + 64'h8; // @[src/main/scala/rpc/RpcTimingChecker.scala 248:33]
  wire [63:0] ear1_g0 = ear1_lower > _ear1_g0_T_1 ? ear1_lower : _ear1_g0_T_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 52:49]
  wire [63:0] _ear1_slot_T_1 = ear1_g0 - prevAt; // @[src/main/scala/rpc/RpcTimingChecker.scala 249:32]
  wire [63:0] _ear1_slot_T_3 = _ear1_slot_T_1 + 64'h7; // @[src/main/scala/rpc/RpcTimingChecker.scala 249:42]
  wire [63:0] _ear1_slot_T_5 = {_ear1_slot_T_3[63:3], 3'h0}; // @[src/main/scala/rpc/RpcTimingChecker.scala 249:82]
  wire [63:0] ear1_slot = prevAt + _ear1_slot_T_5; // @[src/main/scala/rpc/RpcTimingChecker.scala 249:23]
  wire [63:0] _ear1_idleSlot_T_1 = prevAt + 64'h4; // @[src/main/scala/rpc/RpcTimingChecker.scala 250:44]
  wire [63:0] _ear1_idleSlot_T_3 = ear1_lower > _ear1_idleSlot_T_1 ? ear1_lower : _ear1_idleSlot_T_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 52:49]
  wire [63:0] ear1_idleSlot = _ear1_idleSlot_T_3 > idleAt ? _ear1_idleSlot_T_3 : idleAt; // @[src/main/scala/rpc/RpcTimingChecker.scala 52:49]
  wire [63:0] _ear1_T_1 = ear1_slot < ear1_idleSlot ? ear1_slot : ear1_idleSlot; // @[src/main/scala/rpc/RpcTimingChecker.scala 53:49]
  wire [63:0] _ear1_T_2 = anyOpen ? ear1_slot : _ear1_T_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 251:22]
  wire [63:0] ear1 = havePrev ? _ear1_T_2 : ear1_lower; // @[src/main/scala/rpc/RpcTimingChecker.scala 251:8]
  wire [63:0] ear2_lower = bound2 > io_cycle ? bound2 : io_cycle; // @[src/main/scala/rpc/RpcTimingChecker.scala 52:49]
  wire [63:0] ear2_g0 = ear2_lower > _ear1_g0_T_1 ? ear2_lower : _ear1_g0_T_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 52:49]
  wire [63:0] _ear2_slot_T_1 = ear2_g0 - prevAt; // @[src/main/scala/rpc/RpcTimingChecker.scala 249:32]
  wire [63:0] _ear2_slot_T_3 = _ear2_slot_T_1 + 64'h7; // @[src/main/scala/rpc/RpcTimingChecker.scala 249:42]
  wire [63:0] _ear2_slot_T_5 = {_ear2_slot_T_3[63:3], 3'h0}; // @[src/main/scala/rpc/RpcTimingChecker.scala 249:82]
  wire [63:0] ear2_slot = prevAt + _ear2_slot_T_5; // @[src/main/scala/rpc/RpcTimingChecker.scala 249:23]
  wire [63:0] _ear2_idleSlot_T_3 = ear2_lower > _ear1_idleSlot_T_1 ? ear2_lower : _ear1_idleSlot_T_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 52:49]
  wire [63:0] ear2_idleSlot = _ear2_idleSlot_T_3 > idleAt ? _ear2_idleSlot_T_3 : idleAt; // @[src/main/scala/rpc/RpcTimingChecker.scala 52:49]
  wire [63:0] _ear2_T_1 = ear2_slot < ear2_idleSlot ? ear2_slot : ear2_idleSlot; // @[src/main/scala/rpc/RpcTimingChecker.scala 53:49]
  wire [63:0] _ear2_T_2 = anyOpen ? ear2_slot : _ear2_T_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 251:22]
  wire [63:0] ear2 = havePrev ? _ear2_T_2 : ear2_lower; // @[src/main/scala/rpc/RpcTimingChecker.scala 251:8]
  wire  legal1 = ear1 == io_cycle; // @[src/main/scala/rpc/RpcTimingChecker.scala 258:29]
  wire  legal2 = ear2 == io_cycle; // @[src/main/scala/rpc/RpcTimingChecker.scala 259:29]
  wire  _T_227 = io_tckPs < 16'h4e2; // @[src/main/scala/rpc/RpcTimingChecker.scala 264:15]
  wire  _T_228 = mCl == 3'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 110:84]
  wire  _T_229 = mCl == 3'h1; // @[src/main/scala/rpc/RpcTimingChecker.scala 110:84]
  wire  _T_230 = mCl == 3'h2; // @[src/main/scala/rpc/RpcTimingChecker.scala 110:84]
  wire  _T_231 = mCl == 3'h6; // @[src/main/scala/rpc/RpcTimingChecker.scala 110:84]
  wire  _T_235 = ~(mCl == 3'h0 | mCl == 3'h1 | mCl == 3'h2 | mCl == 3'h6); // @[src/main/scala/rpc/RpcTimingChecker.scala 110:46]
  wire  _T_236 = isMrs & _T_235; // @[src/main/scala/rpc/RpcTimingChecker.scala 265:12]
  wire  _T_237 = isMrs & mFixed; // @[src/main/scala/rpc/RpcTimingChecker.scala 266:12]
  wire [15:0] _GEN_15 = _T_228 ? 16'h683 : 16'hffff; // @[src/main/scala/rpc/RpcTimingChecker.scala 112:24 113:{80,84}]
  wire [15:0] _GEN_16 = _T_229 ? 16'h5dc : _GEN_15; // @[src/main/scala/rpc/RpcTimingChecker.scala 113:{80,84}]
  wire [15:0] _GEN_17 = _T_230 ? 16'h4e2 : _GEN_16; // @[src/main/scala/rpc/RpcTimingChecker.scala 113:{80,84}]
  wire [15:0] v = _T_231 ? 16'hfa0 : _GEN_17; // @[src/main/scala/rpc/RpcTimingChecker.scala 113:{80,84}]
  wire  _T_243 = isMrs & tck < v; // @[src/main/scala/rpc/RpcTimingChecker.scala 267:12]
  wire  _T_245 = isRef & f21[1]; // @[src/main/scala/rpc/RpcTimingChecker.scala 268:12]
  wire  _T_248 = (isPre | isRef) & bankMask == 4'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 269:23]
  wire  _T_251 = _T_8 & _T_37; // @[src/main/scala/rpc/RpcTimingChecker.scala 270:17]
  wire  _T_256 = needPrea & ~(isReset | isPre & &bankMask); // @[src/main/scala/rpc/RpcTimingChecker.scala 271:15]
  wire  _T_257 = ~needPrea; // @[src/main/scala/rpc/RpcTimingChecker.scala 272:6]
  wire  _T_259 = isReset | isMrs; // @[src/main/scala/rpc/RpcTimingChecker.scala 272:40]
  wire  _T_261 = ~needPrea & needMrs & ~(isReset | isMrs); // @[src/main/scala/rpc/RpcTimingChecker.scala 272:27]
  wire  _T_268 = zqop == 2'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 273:94]
  wire  _T_272 = everReset & _T_257 & ~needMrs & needZqInit & ~(_T_259 | isZq & zqop == 2'h0); // @[src/main/scala/rpc/RpcTimingChecker.scala 273:55]
  wire  _T_276 = utrMode & ~(isRd | isUtr | isReset); // @[src/main/scala/rpc/RpcTimingChecker.scala 275:14]
  wire  _GEN_20 = 2'h1 == ba ? bankOpen_1 : bankOpen_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 276:{12,12}]
  wire  _GEN_21 = 2'h2 == ba ? bankOpen_2 : _GEN_20; // @[src/main/scala/rpc/RpcTimingChecker.scala 276:{12,12}]
  wire  _GEN_22 = 2'h3 == ba ? bankOpen_3 : _GEN_21; // @[src/main/scala/rpc/RpcTimingChecker.scala 276:{12,12}]
  wire  _T_277 = isAct & _GEN_22; // @[src/main/scala/rpc/RpcTimingChecker.scala 276:12]
  wire  _T_279 = columnAccess & ~_GEN_22; // @[src/main/scala/rpc/RpcTimingChecker.scala 277:19]
  wire [3:0] _T_280 = {bankKnown_3,bankKnown_2,bankKnown_1,bankKnown_0}; // @[src/main/scala/rpc/RpcTimingChecker.scala 278:37]
  wire [3:0] _T_281 = bankMask & _T_280; // @[src/main/scala/rpc/RpcTimingChecker.scala 278:25]
  wire [3:0] _T_283 = ~_anyOpen_T; // @[src/main/scala/rpc/RpcTimingChecker.scala 278:46]
  wire [3:0] _T_284 = _T_281 & _T_283; // @[src/main/scala/rpc/RpcTimingChecker.scala 278:44]
  wire  _T_286 = isPre & |_T_284; // @[src/main/scala/rpc/RpcTimingChecker.scala 278:12]
  wire  _T_287 = isZq & anyOpen; // @[src/main/scala/rpc/RpcTimingChecker.scala 279:11]
  wire  _T_288 = isUtr & anyOpen; // @[src/main/scala/rpc/RpcTimingChecker.scala 280:12]
  wire  _T_290 = isRd & mrZout == 4'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 281:11]
  wire  stateErr = isUndef | _T_227 | _T_236 | _T_237 | _T_243 | _T_245 | _T_248 | _T_251 | _T_256 | _T_261 | _T_272 |
    _T_276 | _T_277 | _T_279 | _T_286 | _T_287 | _T_288 | _T_290; // @[src/main/scala/rpc/RpcTimingChecker.scala 283:57]
  wire [7:0] _stateId_T = _T_290 ? 8'h46 : 8'h0; // @[src/main/scala/chisel3/util/Mux.scala 50:70]
  wire [7:0] _stateId_T_1 = _T_288 ? 8'h32 : _stateId_T; // @[src/main/scala/chisel3/util/Mux.scala 50:70]
  wire [7:0] _stateId_T_2 = _T_287 ? 8'h31 : _stateId_T_1; // @[src/main/scala/chisel3/util/Mux.scala 50:70]
  wire [7:0] _stateId_T_3 = _T_286 ? 8'h30 : _stateId_T_2; // @[src/main/scala/chisel3/util/Mux.scala 50:70]
  wire [7:0] _stateId_T_4 = _T_279 ? 8'h2f : _stateId_T_3; // @[src/main/scala/chisel3/util/Mux.scala 50:70]
  wire [7:0] _stateId_T_5 = _T_277 ? 8'h28 : _stateId_T_4; // @[src/main/scala/chisel3/util/Mux.scala 50:70]
  wire [7:0] _stateId_T_6 = _T_276 ? 8'h3c : _stateId_T_5; // @[src/main/scala/chisel3/util/Mux.scala 50:70]
  wire [7:0] _stateId_T_7 = _T_272 ? 8'hf : _stateId_T_6; // @[src/main/scala/chisel3/util/Mux.scala 50:70]
  wire [7:0] _stateId_T_8 = _T_261 ? 8'he : _stateId_T_7; // @[src/main/scala/chisel3/util/Mux.scala 50:70]
  wire [7:0] _stateId_T_9 = _T_256 ? 8'hd : _stateId_T_8; // @[src/main/scala/chisel3/util/Mux.scala 50:70]
  wire [7:0] _stateId_T_10 = _T_251 ? 8'hb : _stateId_T_9; // @[src/main/scala/chisel3/util/Mux.scala 50:70]
  wire [7:0] _stateId_T_11 = _T_248 ? 8'h6 : _stateId_T_10; // @[src/main/scala/chisel3/util/Mux.scala 50:70]
  wire [7:0] _stateId_T_12 = _T_245 ? 8'h5 : _stateId_T_11; // @[src/main/scala/chisel3/util/Mux.scala 50:70]
  wire [7:0] _stateId_T_13 = _T_243 ? 8'h3 : _stateId_T_12; // @[src/main/scala/chisel3/util/Mux.scala 50:70]
  wire [7:0] _stateId_T_14 = _T_237 ? 8'h4 : _stateId_T_13; // @[src/main/scala/chisel3/util/Mux.scala 50:70]
  wire [7:0] _stateId_T_15 = _T_236 ? 8'h2 : _stateId_T_14; // @[src/main/scala/chisel3/util/Mux.scala 50:70]
  wire [7:0] _stateId_T_16 = _T_227 ? 8'h7 : _stateId_T_15; // @[src/main/scala/chisel3/util/Mux.scala 50:70]
  wire [7:0] stateId = isUndef ? 8'h1 : _stateId_T_16; // @[src/main/scala/chisel3/util/Mux.scala 50:70]
  wire  selR2 = io_refreshSelect == 2'h2; // @[src/main/scala/rpc/RpcTimingChecker.scala 287:40]
  wire  collapse = io_refreshSelect == 2'h1 | selR2; // @[src/main/scala/rpc/RpcTimingChecker.scala 288:51]
  wire [63:0] earSel = selR2 ? ear2 : ear1; // @[src/main/scala/rpc/RpcTimingChecker.scala 289:27]
  wire  legalSel = selR2 ? legal2 : legal1; // @[src/main/scala/rpc/RpcTimingChecker.scala 290:29]
  wire [7:0] _idSel_T_1 = activeAtNow ? 8'h15 : 8'h14; // @[src/main/scala/rpc/RpcTimingChecker.scala 254:29]
  wire [7:0] _idSel_T_2 = io_cycle < bound2 ? id2 : _idSel_T_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 254:8]
  wire [7:0] _idSel_T_5 = io_cycle < bound1 ? id1 : _idSel_T_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 254:8]
  wire [7:0] idSel = selR2 ? _idSel_T_2 : _idSel_T_5; // @[src/main/scala/rpc/RpcTimingChecker.scala 291:26]
  wire [6:0] _cid_T = isPd ? 7'h50 : 7'h1a; // @[src/main/scala/rpc/RpcTimingChecker.scala 306:15]
  wire [63:0] _earliest_T_1 = ear1 > ear2 ? ear1 : ear2; // @[src/main/scala/rpc/RpcTimingChecker.scala 52:49]
  wire [63:0] _earliest_T_2 = isPd ? 64'h0 : _earliest_T_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 307:20]
  wire [1:0] _GEN_23 = isPd ? 2'h3 : 2'h1; // @[src/main/scala/rpc/RpcTimingChecker.scala 312:20 313:10 316:10]
  wire [7:0] _GEN_24 = isPd ? 8'h50 : 8'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 312:20 294:32 314:9]
  wire [1:0] _GEN_25 = ~legalSel ? 2'h2 : _GEN_23; // @[src/main/scala/rpc/RpcTimingChecker.scala 308:25 309:10]
  wire [7:0] _GEN_26 = ~legalSel ? idSel : _GEN_24; // @[src/main/scala/rpc/RpcTimingChecker.scala 308:25 310:9]
  wire [63:0] _GEN_27 = ~legalSel ? earSel : 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 308:25 311:14 295:37]
  wire [1:0] _GEN_28 = refPending & ~collapse & legal1 != legal2 ? 2'h3 : _GEN_25; // @[src/main/scala/rpc/RpcTimingChecker.scala 302:60 305:10]
  wire [7:0] _GEN_29 = refPending & ~collapse & legal1 != legal2 ? {{1'd0}, _cid_T} : _GEN_26; // @[src/main/scala/rpc/RpcTimingChecker.scala 302:60 306:9]
  wire [63:0] _GEN_30 = refPending & ~collapse & legal1 != legal2 ? _earliest_T_2 : _GEN_27; // @[src/main/scala/rpc/RpcTimingChecker.scala 302:60 307:14]
  wire [1:0] _GEN_31 = stateErr ? 2'h2 : _GEN_28; // @[src/main/scala/rpc/RpcTimingChecker.scala 299:24 300:10]
  wire [7:0] _GEN_32 = stateErr ? stateId : _GEN_29; // @[src/main/scala/rpc/RpcTimingChecker.scala 299:24 301:9]
  wire [63:0] _GEN_33 = stateErr ? 64'h0 : _GEN_30; // @[src/main/scala/rpc/RpcTimingChecker.scala 299:24 295:37]
  wire [1:0] kind = ~io_valid ? 2'h0 : _GEN_31; // @[src/main/scala/rpc/RpcTimingChecker.scala 297:19 298:10]
  wire  _io_accepted_T = kind == 2'h1; // @[src/main/scala/rpc/RpcTimingChecker.scala 319:23]
  wire  timingVisible = io_valid & ~stateErr; // @[src/main/scala/rpc/RpcTimingChecker.scala 324:40]
  wire [11:0] _GEN_38 = 2'h1 == ba ? openRow_1 : openRow_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 328:{16,16}]
  wire [11:0] _GEN_39 = 2'h2 == ba ? openRow_2 : _GEN_38; // @[src/main/scala/rpc/RpcTimingChecker.scala 328:{16,16}]
  wire [11:0] _GEN_40 = 2'h3 == ba ? openRow_3 : _GEN_39; // @[src/main/scala/rpc/RpcTimingChecker.scala 328:{16,16}]
  wire [4:0] _GEN_41 = mrCl == 3'h0 ? 5'h8 : 5'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 106:24 107:{59,63}]
  wire [4:0] _GEN_42 = mrCl == 3'h1 ? 5'ha : _GEN_41; // @[src/main/scala/rpc/RpcTimingChecker.scala 107:{59,63}]
  wire [4:0] _GEN_43 = mrCl == 3'h2 ? 5'hb : _GEN_42; // @[src/main/scala/rpc/RpcTimingChecker.scala 107:{59,63}]
  wire [4:0] rl_v = mrCl == 3'h6 ? 5'h3 : _GEN_43; // @[src/main/scala/rpc/RpcTimingChecker.scala 107:{59,63}]
  wire [5:0] rl = 5'h1 + rl_v; // @[src/main/scala/rpc/RpcTimingChecker.scala 331:40]
  wire  commit = io_valid & ~isPd & (_io_accepted_T | kind == 2'h3); // @[src/main/scala/rpc/RpcTimingChecker.scala 335:42]
  wire [63:0] _GEN_326 = {{58'd0}, rl}; // @[src/main/scala/rpc/RpcTimingChecker.scala 336:33]
  wire [63:0] _newBurstEnd_T_1 = io_cycle + _GEN_326; // @[src/main/scala/rpc/RpcTimingChecker.scala 336:33]
  wire [9:0] _newBurstEnd_T_2 = {words, 3'h0}; // @[src/main/scala/rpc/RpcTimingChecker.scala 336:47]
  wire [63:0] _GEN_327 = {{54'd0}, _newBurstEnd_T_2}; // @[src/main/scala/rpc/RpcTimingChecker.scala 336:38]
  wire [63:0] newBurstEnd = _newBurstEnd_T_1 + _GEN_327; // @[src/main/scala/rpc/RpcTimingChecker.scala 336:38]
  wire  _GEN_45 = isReset | everReset; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 344:17 120:34]
  wire  _GEN_47 = isReset | needPrea; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 346:16 122:33]
  wire  _GEN_48 = isReset | needMrs; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 347:15 123:32]
  wire  _GEN_49 = isReset ? 1'h0 : bankOpen_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 349:21 118:57]
  wire  _GEN_50 = isReset ? 1'h0 : bankKnown_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 350:22 118:57]
  wire  _GEN_51 = isReset ? 1'h0 : actValid_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 351:21 118:57]
  wire  _GEN_52 = isReset ? 1'h0 : preValid_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 352:21 118:57]
  wire  _GEN_53 = isReset ? 1'h0 : wrValid_0; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 353:20 118:57]
  wire  _GEN_54 = isReset ? 1'h0 : bankOpen_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 349:21 118:57]
  wire  _GEN_55 = isReset ? 1'h0 : bankKnown_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 350:22 118:57]
  wire  _GEN_56 = isReset ? 1'h0 : actValid_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 351:21 118:57]
  wire  _GEN_57 = isReset ? 1'h0 : preValid_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 352:21 118:57]
  wire  _GEN_58 = isReset ? 1'h0 : wrValid_1; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 353:20 118:57]
  wire  _GEN_59 = isReset ? 1'h0 : bankOpen_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 349:21 118:57]
  wire  _GEN_60 = isReset ? 1'h0 : bankKnown_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 350:22 118:57]
  wire  _GEN_61 = isReset ? 1'h0 : actValid_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 351:21 118:57]
  wire  _GEN_62 = isReset ? 1'h0 : preValid_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 352:21 118:57]
  wire  _GEN_63 = isReset ? 1'h0 : wrValid_2; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 353:20 118:57]
  wire  _GEN_64 = isReset ? 1'h0 : bankOpen_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 349:21 118:57]
  wire  _GEN_65 = isReset ? 1'h0 : bankKnown_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 350:22 118:57]
  wire  _GEN_66 = isReset ? 1'h0 : actValid_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 351:21 118:57]
  wire  _GEN_67 = isReset ? 1'h0 : preValid_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 352:21 118:57]
  wire  _GEN_68 = isReset ? 1'h0 : wrValid_3; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 353:20 118:57]
  wire  _GEN_69 = isReset ? 1'h0 : actAnyValid; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 355:19 138:36]
  wire  _GEN_70 = isReset ? 1'h0 : burstValid; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 356:18 141:35]
  wire  _GEN_71 = isReset ? 1'h0 : modeValid; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 357:17 145:34]
  wire  _GEN_72 = isReset ? 1'h0 : zqValid; // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19 358:15 161:32]
  wire  _GEN_81 = bankMask[0] ? 1'h0 : _GEN_49; // @[src/main/scala/rpc/RpcTimingChecker.scala 370:27 371:23]
  wire  _GEN_82 = bankMask[0] | _GEN_50; // @[src/main/scala/rpc/RpcTimingChecker.scala 370:27 372:24]
  wire  _GEN_83 = bankMask[0] | _GEN_52; // @[src/main/scala/rpc/RpcTimingChecker.scala 370:27 373:23]
  wire  _GEN_85 = bankMask[1] ? 1'h0 : _GEN_54; // @[src/main/scala/rpc/RpcTimingChecker.scala 370:27 371:23]
  wire  _GEN_86 = bankMask[1] | _GEN_55; // @[src/main/scala/rpc/RpcTimingChecker.scala 370:27 372:24]
  wire  _GEN_87 = bankMask[1] | _GEN_57; // @[src/main/scala/rpc/RpcTimingChecker.scala 370:27 373:23]
  wire  _GEN_89 = bankMask[2] ? 1'h0 : _GEN_59; // @[src/main/scala/rpc/RpcTimingChecker.scala 370:27 371:23]
  wire  _GEN_90 = bankMask[2] | _GEN_60; // @[src/main/scala/rpc/RpcTimingChecker.scala 370:27 372:24]
  wire  _GEN_91 = bankMask[2] | _GEN_62; // @[src/main/scala/rpc/RpcTimingChecker.scala 370:27 373:23]
  wire  _GEN_93 = bankMask[3] ? 1'h0 : _GEN_64; // @[src/main/scala/rpc/RpcTimingChecker.scala 370:27 371:23]
  wire  _GEN_94 = bankMask[3] | _GEN_65; // @[src/main/scala/rpc/RpcTimingChecker.scala 370:27 372:24]
  wire  _GEN_95 = bankMask[3] | _GEN_67; // @[src/main/scala/rpc/RpcTimingChecker.scala 370:27 373:23]
  wire  _GEN_97 = isPre ? _GEN_81 : _GEN_49; // @[src/main/scala/rpc/RpcTimingChecker.scala 368:17]
  wire  _GEN_98 = isPre ? _GEN_82 : _GEN_50; // @[src/main/scala/rpc/RpcTimingChecker.scala 368:17]
  wire  _GEN_101 = isPre ? _GEN_85 : _GEN_54; // @[src/main/scala/rpc/RpcTimingChecker.scala 368:17]
  wire  _GEN_102 = isPre ? _GEN_86 : _GEN_55; // @[src/main/scala/rpc/RpcTimingChecker.scala 368:17]
  wire  _GEN_105 = isPre ? _GEN_89 : _GEN_59; // @[src/main/scala/rpc/RpcTimingChecker.scala 368:17]
  wire  _GEN_106 = isPre ? _GEN_90 : _GEN_60; // @[src/main/scala/rpc/RpcTimingChecker.scala 368:17]
  wire  _GEN_109 = isPre ? _GEN_93 : _GEN_64; // @[src/main/scala/rpc/RpcTimingChecker.scala 368:17]
  wire  _GEN_110 = isPre ? _GEN_94 : _GEN_65; // @[src/main/scala/rpc/RpcTimingChecker.scala 368:17]
  wire  _GEN_328 = 2'h0 == ba; // @[src/main/scala/rpc/RpcTimingChecker.scala 380:{20,20}]
  wire  _GEN_114 = 2'h0 == ba | _GEN_97; // @[src/main/scala/rpc/RpcTimingChecker.scala 380:{20,20}]
  wire  _GEN_329 = 2'h1 == ba; // @[src/main/scala/rpc/RpcTimingChecker.scala 380:{20,20}]
  wire  _GEN_115 = 2'h1 == ba | _GEN_101; // @[src/main/scala/rpc/RpcTimingChecker.scala 380:{20,20}]
  wire  _GEN_330 = 2'h2 == ba; // @[src/main/scala/rpc/RpcTimingChecker.scala 380:{20,20}]
  wire  _GEN_116 = 2'h2 == ba | _GEN_105; // @[src/main/scala/rpc/RpcTimingChecker.scala 380:{20,20}]
  wire  _GEN_331 = 2'h3 == ba; // @[src/main/scala/rpc/RpcTimingChecker.scala 380:{20,20}]
  wire  _GEN_117 = 2'h3 == ba | _GEN_109; // @[src/main/scala/rpc/RpcTimingChecker.scala 380:{20,20}]
  wire  _GEN_118 = _GEN_328 | _GEN_98; // @[src/main/scala/rpc/RpcTimingChecker.scala 381:{21,21}]
  wire  _GEN_119 = _GEN_329 | _GEN_102; // @[src/main/scala/rpc/RpcTimingChecker.scala 381:{21,21}]
  wire  _GEN_120 = _GEN_330 | _GEN_106; // @[src/main/scala/rpc/RpcTimingChecker.scala 381:{21,21}]
  wire  _GEN_121 = _GEN_331 | _GEN_110; // @[src/main/scala/rpc/RpcTimingChecker.scala 381:{21,21}]
  wire  _GEN_126 = _GEN_328 | _GEN_51; // @[src/main/scala/rpc/RpcTimingChecker.scala 383:{20,20}]
  wire  _GEN_127 = _GEN_329 | _GEN_56; // @[src/main/scala/rpc/RpcTimingChecker.scala 383:{20,20}]
  wire  _GEN_128 = _GEN_330 | _GEN_61; // @[src/main/scala/rpc/RpcTimingChecker.scala 383:{20,20}]
  wire  _GEN_129 = _GEN_331 | _GEN_66; // @[src/main/scala/rpc/RpcTimingChecker.scala 383:{20,20}]
  wire  _GEN_138 = isAct ? _GEN_118 : _GEN_98; // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
  wire  _GEN_139 = isAct ? _GEN_119 : _GEN_102; // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
  wire  _GEN_140 = isAct ? _GEN_120 : _GEN_106; // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
  wire  _GEN_141 = isAct ? _GEN_121 : _GEN_110; // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
  wire  _GEN_154 = isAct | _GEN_69; // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17 385:19]
  wire  _GEN_156 = isRd | isWr | _GEN_70; // @[src/main/scala/rpc/RpcTimingChecker.scala 388:24 389:18]
  wire  _GEN_159 = _GEN_328 | _GEN_53; // @[src/main/scala/rpc/RpcTimingChecker.scala 394:{19,19}]
  wire  _GEN_160 = _GEN_329 | _GEN_58; // @[src/main/scala/rpc/RpcTimingChecker.scala 394:{19,19}]
  wire  _GEN_161 = _GEN_330 | _GEN_63; // @[src/main/scala/rpc/RpcTimingChecker.scala 394:{19,19}]
  wire  _GEN_162 = _GEN_331 | _GEN_68; // @[src/main/scala/rpc/RpcTimingChecker.scala 394:{19,19}]
  wire  _GEN_182 = isMrs | _GEN_71; // @[src/main/scala/rpc/RpcTimingChecker.scala 397:17 405:17]
  wire  _GEN_183 = isMrs | modeWasMrs; // @[src/main/scala/rpc/RpcTimingChecker.scala 397:17 406:18 146:35]
  wire  _GEN_188 = isUtr | _GEN_182; // @[src/main/scala/rpc/RpcTimingChecker.scala 410:17 413:17]
  wire  _GEN_191 = _T_268 ? 1'h0 : needZqInit; // @[src/main/scala/rpc/RpcTimingChecker.scala 421:26 124:35 421:39]
  wire  _GEN_192 = isZq | _GEN_72; // @[src/main/scala/rpc/RpcTimingChecker.scala 417:16 418:15]
  wire  _GEN_195 = isZq ? _GEN_191 : needZqInit; // @[src/main/scala/rpc/RpcTimingChecker.scala 417:16 124:35]
  wire [1:0] _refBanks_T_4 = bankMask[0] + bankMask[1]; // @[src/main/scala/rpc/RpcTimingChecker.scala 430:27]
  wire [1:0] _refBanks_T_6 = bankMask[2] + bankMask[3]; // @[src/main/scala/rpc/RpcTimingChecker.scala 430:27]
  wire [2:0] _refBanks_T_8 = _refBanks_T_4 + _refBanks_T_6; // @[src/main/scala/rpc/RpcTimingChecker.scala 430:27]
  wire  _GEN_197 = isRef | _GEN_138; // @[src/main/scala/rpc/RpcTimingChecker.scala 423:17 426:22]
  wire  _GEN_199 = isRef | _GEN_139; // @[src/main/scala/rpc/RpcTimingChecker.scala 423:17 426:22]
  wire  _GEN_201 = isRef | _GEN_140; // @[src/main/scala/rpc/RpcTimingChecker.scala 423:17 426:22]
  wire  _GEN_203 = isRef | _GEN_141; // @[src/main/scala/rpc/RpcTimingChecker.scala 423:17 426:22]
  wire  _GEN_209 = commit | havePrev; // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16 339:14 126:33]
  wire  _GEN_272 = commit ? _GEN_195 : needZqInit; // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16 124:35]
  assign io_accepted = kind == 2'h1; // @[src/main/scala/rpc/RpcTimingChecker.scala 319:23]
  assign io_kind = ~io_valid ? 2'h0 : _GEN_31; // @[src/main/scala/rpc/RpcTimingChecker.scala 297:19 298:10]
  assign io_constraintId = ~io_valid ? 8'h0 : _GEN_32; // @[src/main/scala/rpc/RpcTimingChecker.scala 297:19 294:32]
  assign io_earliest = ~io_valid ? 64'h0 : _GEN_33; // @[src/main/scala/rpc/RpcTimingChecker.scala 297:19 295:37]
  assign io_opCode = 3'h0 == rise[2:0] ? _op_T : _GEN_5; // @[src/main/scala/rpc/RpcTimingChecker.scala 63:22 64:18]
  assign io_earliestRs1 = timingVisible ? ear1 : 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 325:24]
  assign io_earliestRs2 = timingVisible ? ear2 : 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 326:24]
  assign io_bank = rise[4:3]; // @[src/main/scala/rpc/RpcTimingChecker.scala 87:24]
  assign io_row = isAct ? actRow : _GEN_40; // @[src/main/scala/rpc/RpcTimingChecker.scala 328:16]
  assign io_column = {fall[15:13],rise[15:13]}; // @[src/main/scala/rpc/RpcTimingChecker.scala 89:24]
  assign io_words = rise[10:5] + 6'h1; // @[src/main/scala/rpc/RpcTimingChecker.scala 90:35]
  assign io_latency = rl[4:0]; // @[src/main/scala/rpc/RpcTimingChecker.scala 332:14]
  always @(posedge clock) begin
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 120:34]
      everReset <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 120:34]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      everReset <= _GEN_45;
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 121:32]
      resetAt <= 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 121:32]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isReset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19]
        resetAt <= io_cycle; // @[src/main/scala/rpc/RpcTimingChecker.scala 345:15]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 122:33]
      needPrea <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 122:33]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isPre) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 368:17]
        needPrea <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 377:16]
      end else begin
        needPrea <= _GEN_47;
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 123:32]
      needMrs <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 123:32]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isMrs) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 397:17]
        needMrs <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 408:15]
      end else begin
        needMrs <= _GEN_48;
      end
    end
    needZqInit <= reset | _GEN_272; // @[src/main/scala/rpc/RpcTimingChecker.scala 124:{35,35}]
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 126:33]
      havePrev <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 126:33]
    end else begin
      havePrev <= _GEN_209;
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 127:31]
      prevAt <= 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 127:31]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      prevAt <= io_cycle; // @[src/main/scala/rpc/RpcTimingChecker.scala 340:12]
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      bankOpen_0 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isRef) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 423:17]
        bankOpen_0 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 425:21]
      end else if (isAct) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
        bankOpen_0 <= _GEN_114;
      end else begin
        bankOpen_0 <= _GEN_97;
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      bankOpen_1 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isRef) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 423:17]
        bankOpen_1 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 425:21]
      end else if (isAct) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
        bankOpen_1 <= _GEN_115;
      end else begin
        bankOpen_1 <= _GEN_101;
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      bankOpen_2 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isRef) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 423:17]
        bankOpen_2 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 425:21]
      end else if (isAct) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
        bankOpen_2 <= _GEN_116;
      end else begin
        bankOpen_2 <= _GEN_105;
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      bankOpen_3 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isRef) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 423:17]
        bankOpen_3 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 425:21]
      end else if (isAct) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
        bankOpen_3 <= _GEN_117;
      end else begin
        bankOpen_3 <= _GEN_109;
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      bankKnown_0 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      bankKnown_0 <= _GEN_197;
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      bankKnown_1 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      bankKnown_1 <= _GEN_199;
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      bankKnown_2 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      bankKnown_2 <= _GEN_201;
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      bankKnown_3 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      bankKnown_3 <= _GEN_203;
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      openRow_0 <= 12'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isAct) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
        if (2'h0 == ba) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 382:19]
          openRow_0 <= actRow; // @[src/main/scala/rpc/RpcTimingChecker.scala 382:19]
        end
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      openRow_1 <= 12'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isAct) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
        if (2'h1 == ba) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 382:19]
          openRow_1 <= actRow; // @[src/main/scala/rpc/RpcTimingChecker.scala 382:19]
        end
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      openRow_2 <= 12'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isAct) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
        if (2'h2 == ba) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 382:19]
          openRow_2 <= actRow; // @[src/main/scala/rpc/RpcTimingChecker.scala 382:19]
        end
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      openRow_3 <= 12'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isAct) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
        if (2'h3 == ba) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 382:19]
          openRow_3 <= actRow; // @[src/main/scala/rpc/RpcTimingChecker.scala 382:19]
        end
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      actValid_0 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isAct) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
        actValid_0 <= _GEN_126;
      end else if (isReset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19]
        actValid_0 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 351:21]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      actValid_1 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isAct) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
        actValid_1 <= _GEN_127;
      end else if (isReset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19]
        actValid_1 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 351:21]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      actValid_2 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isAct) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
        actValid_2 <= _GEN_128;
      end else if (isReset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19]
        actValid_2 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 351:21]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      actValid_3 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isAct) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
        actValid_3 <= _GEN_129;
      end else if (isReset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19]
        actValid_3 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 351:21]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      actAt_0 <= 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isAct) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
        if (2'h0 == ba) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 384:17]
          actAt_0 <= io_cycle; // @[src/main/scala/rpc/RpcTimingChecker.scala 384:17]
        end
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      actAt_1 <= 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isAct) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
        if (2'h1 == ba) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 384:17]
          actAt_1 <= io_cycle; // @[src/main/scala/rpc/RpcTimingChecker.scala 384:17]
        end
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      actAt_2 <= 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isAct) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
        if (2'h2 == ba) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 384:17]
          actAt_2 <= io_cycle; // @[src/main/scala/rpc/RpcTimingChecker.scala 384:17]
        end
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      actAt_3 <= 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isAct) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
        if (2'h3 == ba) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 384:17]
          actAt_3 <= io_cycle; // @[src/main/scala/rpc/RpcTimingChecker.scala 384:17]
        end
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      preValid_0 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isPre) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 368:17]
        preValid_0 <= _GEN_83;
      end else if (isReset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19]
        preValid_0 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 352:21]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      preValid_1 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isPre) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 368:17]
        preValid_1 <= _GEN_87;
      end else if (isReset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19]
        preValid_1 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 352:21]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      preValid_2 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isPre) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 368:17]
        preValid_2 <= _GEN_91;
      end else if (isReset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19]
        preValid_2 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 352:21]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      preValid_3 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isPre) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 368:17]
        preValid_3 <= _GEN_95;
      end else if (isReset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19]
        preValid_3 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 352:21]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      preAt_0 <= 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isPre) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 368:17]
        if (bankMask[0]) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 370:27]
          preAt_0 <= io_cycle; // @[src/main/scala/rpc/RpcTimingChecker.scala 374:20]
        end
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      preAt_1 <= 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isPre) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 368:17]
        if (bankMask[1]) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 370:27]
          preAt_1 <= io_cycle; // @[src/main/scala/rpc/RpcTimingChecker.scala 374:20]
        end
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      preAt_2 <= 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isPre) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 368:17]
        if (bankMask[2]) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 370:27]
          preAt_2 <= io_cycle; // @[src/main/scala/rpc/RpcTimingChecker.scala 374:20]
        end
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      preAt_3 <= 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isPre) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 368:17]
        if (bankMask[3]) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 370:27]
          preAt_3 <= io_cycle; // @[src/main/scala/rpc/RpcTimingChecker.scala 374:20]
        end
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      wrValid_0 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isWr) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 393:16]
        wrValid_0 <= _GEN_159;
      end else if (isReset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19]
        wrValid_0 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 353:20]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      wrValid_1 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isWr) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 393:16]
        wrValid_1 <= _GEN_160;
      end else if (isReset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19]
        wrValid_1 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 353:20]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      wrValid_2 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isWr) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 393:16]
        wrValid_2 <= _GEN_161;
      end else if (isReset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19]
        wrValid_2 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 353:20]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      wrValid_3 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isWr) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 393:16]
        wrValid_3 <= _GEN_162;
      end else if (isReset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19]
        wrValid_3 <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 353:20]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      wrEndAt_0 <= 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isWr) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 393:16]
        if (2'h0 == ba) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 395:19]
          wrEndAt_0 <= newBurstEnd; // @[src/main/scala/rpc/RpcTimingChecker.scala 395:19]
        end
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      wrEndAt_1 <= 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isWr) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 393:16]
        if (2'h1 == ba) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 395:19]
          wrEndAt_1 <= newBurstEnd; // @[src/main/scala/rpc/RpcTimingChecker.scala 395:19]
        end
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      wrEndAt_2 <= 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isWr) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 393:16]
        if (2'h2 == ba) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 395:19]
          wrEndAt_2 <= newBurstEnd; // @[src/main/scala/rpc/RpcTimingChecker.scala 395:19]
        end
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
      wrEndAt_3 <= 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 118:57]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isWr) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 393:16]
        if (2'h3 == ba) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 395:19]
          wrEndAt_3 <= newBurstEnd; // @[src/main/scala/rpc/RpcTimingChecker.scala 395:19]
        end
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 138:36]
      actAnyValid <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 138:36]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      actAnyValid <= _GEN_154;
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 139:33]
      actAnyAt <= 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 139:33]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isAct) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 379:17]
        actAnyAt <= io_cycle; // @[src/main/scala/rpc/RpcTimingChecker.scala 386:16]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 141:35]
      burstValid <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 141:35]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      burstValid <= _GEN_156;
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 142:35]
      burstWrite <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 142:35]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isRd | isWr) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 388:24]
        burstWrite <= isWr; // @[src/main/scala/rpc/RpcTimingChecker.scala 390:18]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 143:33]
      burstEnd <= 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 143:33]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isRd | isWr) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 388:24]
        burstEnd <= newBurstEnd; // @[src/main/scala/rpc/RpcTimingChecker.scala 391:16]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 145:34]
      modeValid <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 145:34]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      modeValid <= _GEN_188;
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 146:35]
      modeWasMrs <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 146:35]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isUtr) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 410:17]
        modeWasMrs <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 414:18]
      end else begin
        modeWasMrs <= _GEN_183;
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 147:31]
      modeAt <= 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 147:31]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isUtr) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 410:17]
        modeAt <= io_cycle; // @[src/main/scala/rpc/RpcTimingChecker.scala 415:14]
      end else if (isMrs) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 397:17]
        modeAt <= io_cycle; // @[src/main/scala/rpc/RpcTimingChecker.scala 407:14]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 150:29]
      mrCl <= 3'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 150:29]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isMrs) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 397:17]
        mrCl <= mCl; // @[src/main/scala/rpc/RpcTimingChecker.scala 398:12]
      end else if (isReset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19]
        mrCl <= 3'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 360:12]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 152:31]
      mrZout <= 4'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 152:31]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isMrs) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 397:17]
        mrZout <= mZout; // @[src/main/scala/rpc/RpcTimingChecker.scala 400:14]
      end else if (isReset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19]
        mrZout <= 4'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 362:14]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 155:32]
      mrCsrfx <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 155:32]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isMrs) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 397:17]
        mrCsrfx <= mCsrfx; // @[src/main/scala/rpc/RpcTimingChecker.scala 403:15]
      end else if (isReset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19]
        mrCsrfx <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 365:15]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 158:32]
      utrMode <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 158:32]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isUtr) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 410:17]
        utrMode <= utrEn; // @[src/main/scala/rpc/RpcTimingChecker.scala 411:15]
      end else if (isReset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 343:19]
        utrMode <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 359:15]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 161:32]
      zqValid <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 161:32]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      zqValid <= _GEN_192;
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 162:29]
      zqAt <= 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 162:29]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isZq) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 417:16]
        zqAt <= io_cycle; // @[src/main/scala/rpc/RpcTimingChecker.scala 419:12]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 163:30]
      zqOpR <= 2'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 163:30]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isZq) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 417:16]
        zqOpR <= zqop; // @[src/main/scala/rpc/RpcTimingChecker.scala 420:13]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 165:35]
      refPending <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 165:35]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      refPending <= isRef;
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 166:30]
      refAt <= 64'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 166:30]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isRef) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 423:17]
        refAt <= io_cycle; // @[src/main/scala/rpc/RpcTimingChecker.scala 429:13]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 167:33]
      refBanks <= 3'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 167:33]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isRef) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 423:17]
        refBanks <= _refBanks_T_8; // @[src/main/scala/rpc/RpcTimingChecker.scala 430:16]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 168:30]
      refLp <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 168:30]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isRef) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 423:17]
        refLp <= f21[0]; // @[src/main/scala/rpc/RpcTimingChecker.scala 431:13]
      end
    end
    if (reset) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 169:32]
      refLoop <= 1'h0; // @[src/main/scala/rpc/RpcTimingChecker.scala 169:32]
    end else if (commit) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 338:16]
      if (isRef) begin // @[src/main/scala/rpc/RpcTimingChecker.scala 423:17]
        refLoop <= mrCsrfx; // @[src/main/scala/rpc/RpcTimingChecker.scala 432:15]
      end
    end
  end
// Register and memory initialization
`ifdef RANDOMIZE_GARBAGE_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_INVALID_ASSIGN
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_REG_INIT
`define RANDOMIZE
`endif
`ifdef RANDOMIZE_MEM_INIT
`define RANDOMIZE
`endif
`ifndef RANDOM
`define RANDOM $random
`endif
`ifdef RANDOMIZE_MEM_INIT
  integer initvar;
`endif
`ifndef SYNTHESIS
`ifdef FIRRTL_BEFORE_INITIAL
`FIRRTL_BEFORE_INITIAL
`endif
initial begin
  `ifdef RANDOMIZE
    `ifdef INIT_RANDOM
      `INIT_RANDOM
    `endif
    `ifndef VERILATOR
      `ifdef RANDOMIZE_DELAY
        #`RANDOMIZE_DELAY begin end
      `else
        #0.002 begin end
      `endif
    `endif
`ifdef RANDOMIZE_REG_INIT
  _RAND_0 = {1{`RANDOM}};
  everReset = _RAND_0[0:0];
  _RAND_1 = {2{`RANDOM}};
  resetAt = _RAND_1[63:0];
  _RAND_2 = {1{`RANDOM}};
  needPrea = _RAND_2[0:0];
  _RAND_3 = {1{`RANDOM}};
  needMrs = _RAND_3[0:0];
  _RAND_4 = {1{`RANDOM}};
  needZqInit = _RAND_4[0:0];
  _RAND_5 = {1{`RANDOM}};
  havePrev = _RAND_5[0:0];
  _RAND_6 = {2{`RANDOM}};
  prevAt = _RAND_6[63:0];
  _RAND_7 = {1{`RANDOM}};
  bankOpen_0 = _RAND_7[0:0];
  _RAND_8 = {1{`RANDOM}};
  bankOpen_1 = _RAND_8[0:0];
  _RAND_9 = {1{`RANDOM}};
  bankOpen_2 = _RAND_9[0:0];
  _RAND_10 = {1{`RANDOM}};
  bankOpen_3 = _RAND_10[0:0];
  _RAND_11 = {1{`RANDOM}};
  bankKnown_0 = _RAND_11[0:0];
  _RAND_12 = {1{`RANDOM}};
  bankKnown_1 = _RAND_12[0:0];
  _RAND_13 = {1{`RANDOM}};
  bankKnown_2 = _RAND_13[0:0];
  _RAND_14 = {1{`RANDOM}};
  bankKnown_3 = _RAND_14[0:0];
  _RAND_15 = {1{`RANDOM}};
  openRow_0 = _RAND_15[11:0];
  _RAND_16 = {1{`RANDOM}};
  openRow_1 = _RAND_16[11:0];
  _RAND_17 = {1{`RANDOM}};
  openRow_2 = _RAND_17[11:0];
  _RAND_18 = {1{`RANDOM}};
  openRow_3 = _RAND_18[11:0];
  _RAND_19 = {1{`RANDOM}};
  actValid_0 = _RAND_19[0:0];
  _RAND_20 = {1{`RANDOM}};
  actValid_1 = _RAND_20[0:0];
  _RAND_21 = {1{`RANDOM}};
  actValid_2 = _RAND_21[0:0];
  _RAND_22 = {1{`RANDOM}};
  actValid_3 = _RAND_22[0:0];
  _RAND_23 = {2{`RANDOM}};
  actAt_0 = _RAND_23[63:0];
  _RAND_24 = {2{`RANDOM}};
  actAt_1 = _RAND_24[63:0];
  _RAND_25 = {2{`RANDOM}};
  actAt_2 = _RAND_25[63:0];
  _RAND_26 = {2{`RANDOM}};
  actAt_3 = _RAND_26[63:0];
  _RAND_27 = {1{`RANDOM}};
  preValid_0 = _RAND_27[0:0];
  _RAND_28 = {1{`RANDOM}};
  preValid_1 = _RAND_28[0:0];
  _RAND_29 = {1{`RANDOM}};
  preValid_2 = _RAND_29[0:0];
  _RAND_30 = {1{`RANDOM}};
  preValid_3 = _RAND_30[0:0];
  _RAND_31 = {2{`RANDOM}};
  preAt_0 = _RAND_31[63:0];
  _RAND_32 = {2{`RANDOM}};
  preAt_1 = _RAND_32[63:0];
  _RAND_33 = {2{`RANDOM}};
  preAt_2 = _RAND_33[63:0];
  _RAND_34 = {2{`RANDOM}};
  preAt_3 = _RAND_34[63:0];
  _RAND_35 = {1{`RANDOM}};
  wrValid_0 = _RAND_35[0:0];
  _RAND_36 = {1{`RANDOM}};
  wrValid_1 = _RAND_36[0:0];
  _RAND_37 = {1{`RANDOM}};
  wrValid_2 = _RAND_37[0:0];
  _RAND_38 = {1{`RANDOM}};
  wrValid_3 = _RAND_38[0:0];
  _RAND_39 = {2{`RANDOM}};
  wrEndAt_0 = _RAND_39[63:0];
  _RAND_40 = {2{`RANDOM}};
  wrEndAt_1 = _RAND_40[63:0];
  _RAND_41 = {2{`RANDOM}};
  wrEndAt_2 = _RAND_41[63:0];
  _RAND_42 = {2{`RANDOM}};
  wrEndAt_3 = _RAND_42[63:0];
  _RAND_43 = {1{`RANDOM}};
  actAnyValid = _RAND_43[0:0];
  _RAND_44 = {2{`RANDOM}};
  actAnyAt = _RAND_44[63:0];
  _RAND_45 = {1{`RANDOM}};
  burstValid = _RAND_45[0:0];
  _RAND_46 = {1{`RANDOM}};
  burstWrite = _RAND_46[0:0];
  _RAND_47 = {2{`RANDOM}};
  burstEnd = _RAND_47[63:0];
  _RAND_48 = {1{`RANDOM}};
  modeValid = _RAND_48[0:0];
  _RAND_49 = {1{`RANDOM}};
  modeWasMrs = _RAND_49[0:0];
  _RAND_50 = {2{`RANDOM}};
  modeAt = _RAND_50[63:0];
  _RAND_51 = {1{`RANDOM}};
  mrCl = _RAND_51[2:0];
  _RAND_52 = {1{`RANDOM}};
  mrZout = _RAND_52[3:0];
  _RAND_53 = {1{`RANDOM}};
  mrCsrfx = _RAND_53[0:0];
  _RAND_54 = {1{`RANDOM}};
  utrMode = _RAND_54[0:0];
  _RAND_55 = {1{`RANDOM}};
  zqValid = _RAND_55[0:0];
  _RAND_56 = {2{`RANDOM}};
  zqAt = _RAND_56[63:0];
  _RAND_57 = {1{`RANDOM}};
  zqOpR = _RAND_57[1:0];
  _RAND_58 = {1{`RANDOM}};
  refPending = _RAND_58[0:0];
  _RAND_59 = {2{`RANDOM}};
  refAt = _RAND_59[63:0];
  _RAND_60 = {1{`RANDOM}};
  refBanks = _RAND_60[2:0];
  _RAND_61 = {1{`RANDOM}};
  refLp = _RAND_61[0:0];
  _RAND_62 = {1{`RANDOM}};
  refLoop = _RAND_62[0:0];
`endif // RANDOMIZE_REG_INIT
  `endif // RANDOMIZE
end // initial
`ifdef FIRRTL_AFTER_INITIAL
`FIRRTL_AFTER_INITIAL
`endif
`endif // SYNTHESIS
endmodule
