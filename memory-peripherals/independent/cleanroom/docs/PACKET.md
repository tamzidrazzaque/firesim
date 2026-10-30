# Parallel request packet layout

Source: EM6GA16L Rev. 1.4, Table 7-1 (Parallel Packet Command Truth
Table), Table 7-2 (MRS), Table 7-3 (Burst Count), Table 7-4 (ZQCOP),
Table 7-5 (REFOP), Table 7-6 (UTREN), sections 3.1, 3.9 and 3.10.

A parallel request packet is DB[15:0] sampled on one CLK rising edge
(CK_n rising) and DB[15:0] sampled on the following falling edge, with
CS# low on both edges (Table 7-1). The `packet` input and the JSONL
`packet_hex` field carry both samples in one 32-bit word:

| `packet` bits | Meaning |
|---|---|
| `[15:0]` | DB[15:0] on the rising edge (`R.DBn` below) |
| `[31:16]` | DB[15:0] on the falling edge (`F.DBn` below) |

So `F.DBn` is `packet[16 + n]`. Example: `00540005` is rising
`0x0005`, falling `0x0054`.

`X` (don't care) bits are ignored by the decoder. The `rpc.Packet`
helper writes 0 there.

## Opcode decode

The opcode is `R.DB[2:0]` together with `F.DB0`. For `R.DB[2:0] = 010`
with `F.DB0 = 1` it is also `F.DB[2:1]`.

| Command | R.DB[2:0] | F.DB[2:0] | `opCode` | Name printed by Replay |
|---|---|---|---|---|
| RD | 000 | xx0 | 3 | `RD` |
| RESET | 000 | xx1 | 10 | `RESET` |
| WR | 001 | xx0 | 4 | `WR` |
| ZQ calibration | 001 | xx1 | 9 | `ZQ` |
| MRS | 010 | xx0 | 1 | `MRS` |
| PD Entry | 010 | 001 | 7 | `PD_ENTRY` |
| DPD Entry | 010 | 101 | 8 | `DPD_ENTRY` |
| PRE | 100 | xx0 | 5 | `PRE` |
| ACT | 101 | xx0 | 2 | `ACT` |
| REF | 110 | xx0 | 6 | `REF` |
| UTR | 111 | xx0 | 11 | `UTR` |
| (unassigned) | 011, or 1xx with F.DB0 = 1, or 010 with F.DB[2:0] = 011 / 111 | | 15 | `UNDEFINED` |

The table has no row for any unassigned combination, so the checker
reports it as `VIOLATION constraint=PKT_UNDEFINED_OPCODE earliest=na`.
PD Exit and DPD Exit are signalled by CS# high with no packet (Table
7-1), so they cannot be offered. WL-2 / WL-1 rows of Table 7-1 are data
mask beats on DB during a write, not request packets (see "Write data
mask" below).

## Fields per command

### ACT (Table 7-1)

| Field | Bits | Notes |
|---|---|---|
| BA[1:0] | R.DB4 = BA1, R.DB3 = BA0 | bank 0..3 |
| RA[11:0] | F.DB12 = RA11 ... F.DB1 = RA0 | row 0..4095 (Table 1-2) |

### RD / WR (Tables 7-1 and 7-3)

| Field | Bits | Notes |
|---|---|---|
| BA[1:0] | R.DB4, R.DB3 | bank |
| BC[5:0] | R.DB10 = BC5 ... R.DB5 = BC0 | burst length = BC + 1 WORDs (1..64), section 3.10 |
| CA[6:4] | R.DB15 = CA6, R.DB14 = CA5, R.DB13 = CA4 | |
| CA[9:7] | F.DB15 = CA9, F.DB14 = CA8, F.DB13 = CA7 | |

CA[9:4] is the 32-byte WORD address within the 2 KB page. CA[3:0] are
not carried because a WORD is the smallest transfer (Table 1-2, section
2.4). The checker reports `column` = CA[9:4] (0..63) and `words` = BC + 1.
Bursts wrap inside the page (section 3.1).

### PRE (Table 7-1)

| Field | Bits |
|---|---|
| BK3..BK0 | R.DB9 = BK3, R.DB8 = BK2, R.DB7 = BK1, R.DB6 = BK0 |

A set bit selects that bank. `000003c4` is PRE for all four banks
(Precharge All). An all-zero mask selects no bank. The checker rejects
it (`PKT_NO_BANK`); see docs/AMBIGUITY.md.

### REF (Tables 7-1 and 7-5)

| Field | Bits | Values |
|---|---|---|
| BK3..BK0 | R.DB9..R.DB6 | banks to refresh |
| REFOP1, REFOP0 | F.DB2, F.DB1 | 00 = FST (tREFI 100 ns), 01 = LP (tREFI 3.2 us), 1x = reserved |

One-shot or loop refresh is not in the REF packet. It comes from the
CSRFX field of the last MRS.

### MRS (Tables 7-1 and 7-2)

| Field | Bits | Encoding |
|---|---|---|
| CL | R.DB[5:3] | 000 = 8 (default), 001 = 10, 010 = 11, 110 = 3, others reserved |
| nWR | R.DB[8:6] | 000 = 4, 001 = 6, 010 = 7, 011 = 8 (default), 100 = 10, 101 = 12, 110 = 14, 111 = 16 |
| Zout | R.DB[12:9] | xxx1 = 23.7 ohm, 0000 = open (default), 0010 = 120, 0100 = 90, 0110 = 51.4, 1000 = 60, 1010 = 40, 1100 = 36, 1110 = 27.7 ohm |
| ODT | R.DB[15:13] | 000 = open, 001 = 60, 010 = 45, 011 = 25.7, 100 = 30, 101 = 20, 110 = 18, 111 = 13.85 ohm |
| STBODT | F.DB12 | 0 = disabled (default), 1 = enabled |
| CSRFX | F.DB13 | 0 = one-shot refresh (default), 1 = loop refresh |
| ODTPD | F.DB14 | 0 = ODT off in PD (default), 1 = on |
| (fixed 0) | F.DB15 | must be 0 |

RL = WL = AL + CL with AL = 1 (Table 7-2). The checker uses CL for read
and write latency, CSRFX for the refresh completion bound and Zout = open
to reject reads. Table 11-3 gives a minimum tCK for each CL, so the
checker rejects an MRS whose CL is reserved (`MRS_CL_RESERVED`), whose
CL is not allowed at the configured tCK (`MRS_CL_TCK`), or with
F.DB15 = 1 (`MRS_RESERVED_BIT`). The checker decodes and stores nWR,
ODT, STBODT and ODTPD but no modeled rule depends on them (see
docs/AMBIGUITY.md).

Example: `000002d2` = CL 11 (code 010), nWR 8 (code 011),
Zout 23.7 ohm (code 0001), ODT open, CSRFX 0.

### ZQ calibration (Tables 7-1 and 7-4)

| Field | Bits | Values |
|---|---|---|
| ZQCOP1, ZQCOP0 | R.DB15, R.DB14 | 00 = ZQINIT, 01 = ZQCL, 10 = ZQCS, 11 = ZQRESET |

### UTR (Tables 7-1 and 7-6)

| Field | Bits | Values |
|---|---|---|
| UTREN | R.DB3 | 1 = enter UTR mode, 0 = leave |
| UTROP1, UTROP0 | R.DB5, R.DB4 | data pattern 00 = 0101..., 01 = 1100..., 10 = 0011..., 11 = 1010... |

The pattern only affects read data, which the checker does not produce.

### RESET, PD Entry, DPD Entry

No fields besides the opcode.

## Write data mask (not a packet)

The WL-2 and WL-1 rows of Table 7-1 carry DM bits for the first and last
WORD of a write burst on DB. Section 2.7 and Table 2-2 describe them.
Each DM bit masks one byte. They are data-path beats, not request
packets, so the checker never sees them. The `rpc.ArrayModel` helper
takes them as two 32-bit masks (`firstMask`, `lastMask`; set bit =
byte not written) when the caller applies an accepted WR.

## Encoders

`rpc.Packet` (src/main/scala/rpc/Packet.scala) builds these packets for
tests and for writing JSONL. Examples:

| Call | Hex |
|---|---|
| `Packet.reset` | `00010000` |
| `Packet.preAll` | `000003c4` |
| `Packet.mrs(11)` | `000002d2` |
| `Packet.zq(0)` | `00010001` |
| `Packet.act(0, 0x2a)` | `00540005` |
| `Packet.rd(0, 5)` | `0000a000` |
| `Packet.wr(0, 6)` | `0000c001` |
| `Packet.pre(1)` | `00000044` |
| `Packet.ref(1)` | `00000046` |
| `Packet.ref(0xf, 1)` | `000203c6` |
| `Packet.pdEntry` | `00010002` |
| `Packet.dpdEntry` | `00050002` |
