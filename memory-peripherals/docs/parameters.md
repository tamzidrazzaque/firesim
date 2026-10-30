# Parameter catalog

Kind is `specified` when the datasheet states the number, `inferred` when it is derived from a stated rule or from a second public source, and `approximation` when the model chooses a value the datasheet does not pin down.

## HyperRAM (S80KS2562-class, 200 MHz 1.8 V)

| Parameter | Value | Unit | Kind | Source | Notes |
|---|---|---|---|---|---|
| `size_bytes` | 33554432 | B | specified | Infineon HyperRAM 2.0 / S80KS2562 family (1.8 V, 200 MHz column), density 256 Mbit | S80KS2562 is 256 Mbit = 32 MiB. |
| `row_bytes` | 1024 | B | specified | S80KS2562 Rev. *C, Table 5 and section 6.2.1 | 512 words per row, 2 bytes per word, 32768 rows. |
| `tck_ps` | 5000 | ps | specified | Infineon HyperRAM 2.0 / S80KS2562 family (1.8 V, 200 MHz column), tCK max frequency 200 MHz | S80KS2562GABHB020 is the 200 MHz 1.8 V grade. |
| `tCSHI_ps` | 6000 | ps | specified | Infineon HyperRAM 2.0 / S80KS2562 family (1.8 V, 200 MHz column), tCSHI | Minimum CS# high between transactions. 6.0 ns at 200 MHz. |
| `tRWR_ps` | 35000 | ps | specified | Infineon HyperRAM 2.0 / S80KS2562 family (1.8 V, 200 MHz column), tRWR | Read-to-write recovery, CS# high. 35 ns at the 200 MHz 1.8 V column. |
| `tRP_ps` | 200000 | ps | specified | Infineon HyperRAM 2.0 / S80KS2562 family (1.8 V, 200 MHz column), tRP | RESET# pulse width. Not a DRAM precharge. 200 ns. |
| `tRH_ps` | 200000 | ps | specified | Infineon HyperRAM 2.0 / S80KS2562 family (1.8 V, 200 MHz column), tRH | RESET# high to first CS#. 200 ns at this speed grade. |
| `tCSM_ps` | 4000000 | ps | specified | Infineon HyperRAM 2.0 / S80KS2562 family (1.8 V, 200 MHz column), tCSM | Maximum CS# low. 4 us industrial. The device cannot refresh while selected. |
| `tRFH_ps` | 35000 | ps | specified | Infineon HyperRAM 2.0 / S80KS2562 family (1.8 V, 200 MHz column), tRFH | Distributed-refresh time for one row. Equals tACC at 200 MHz (35 ns). |
| `tACC_ps` | 35000 | ps | specified | Infineon HyperRAM 2.0 / S80KS2562 family (1.8 V, 200 MHz column), tACC | Initial access time. 7 CK * 5 ns = 35 ns at the default latency code. |
| `refresh_phase` | reset origin | assumption | approximation | S80KS2562 Rev. *C, section 6.3.2 | The maximum adjacent refresh interval is tCSM: 4 µs at or below 85 °C, 1 µs above. The internal phase is not published; the Python performance model chooses reset as phase zero. SV tests inject either latency explicitly. |
| `ca_ck` | 3 | CK | specified | HyperBus specification, CA phase | 48-bit command/address, DDR, 3 CK. |
| `cr0_reset` | 0x8F2F | code | specified | Infineon HyperRAM 2.0 / S80KS2562 family (1.8 V, 200 MHz column), CR0 power-on | Latency code 0010 = 7 CK, fixed latency, legacy 32-byte wrap. Same encoding as the 1.8 V 200 MHz HyperRAM 2.0 default. |
| `cr1_reset` | 0xFFC1 | code | specified | Infineon HyperRAM 2.0 / S80KS2562 family (1.8 V, 200 MHz column), CR1 power-on | Partial refresh = full array, DRI selects 4 us tCSM. |
| `id0_reset` | 0x0E86 | code | specified | Infineon S80KS2562 datasheet, section 6.2.1 | Identification Register 0. Read-only. |
| `ca_map` | CA[47]=R/W#, CA[46]=AS, CA[45]=burst, CA[44:16]=row/upper col, CA[2:0]=lower col | bits | specified | HyperBus specification, 48-bit CA | AS=0 memory, AS=1 register. Burst type 0 = wrapped, 1 = linear. |
| `rwds_mask` | RWDS high masks the byte on a write | level | specified | HyperBus specification, RWDS | Read data uses RWDS as the strobe. Write data uses RWDS as an active-high mask. |
| `variable_latency` | 2x initial latency when a refresh collides | CK | specified | Infineon HyperRAM 2.0 / S80KS2562 family (1.8 V, 200 MHz column), initial latency / RWDS during CA | Fixed-latency mode (CR0[3]=1) always waits 2x and drives RWDS high during CA. |

## RPC DRAM speed-1600

| Parameter | Value | Unit | Kind | Source | Notes |
|---|---|---|---|---|---|
| `n_banks` | 4 | banks | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Table 1-2, p.5 | BA[1:0]. |
| `n_rows` | 4096 | rows | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Table 1-2, p.5 | RA[11:0]. |
| `page_bytes` | 2048 | B | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Table 1-2, p.5 | Page size 2 KB. CA[9:0], CA[3:0] not applied because BL=16. |
| `word_bytes` | 32 | B | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Fig 2-14, p.30 | One word is 16 bus samples on the x16 DDR bus. |
| `tck_ps` | 1250 | ps | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Table 11-3, p.59 | Speed-1600, CL=11, 800 MHz, 1600 MT/s/pin. |
| `cl` | 11 | CK | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Table 11-3, p.59 | Required CL at 800 MHz. MRS default code is CL=8; the speed grade overrides it. |
| `al` | 1 | CK | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Table 7-2, p.51 | RL = AL + CL with AL fixed at 1. WL = RL. |
| `tRCD_ps` | 13750 | ps | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Table 11-3, p.59 | 11 CK at 1.25 ns. |
| `tRP_ps` | 13750 | ps | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Table 11-3, p.59 | PRE command period. |
| `tRC_ps` | 48750 | ps | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Table 11-3, p.59 | ACT to ACT or REF, same bank. |
| `tRAS_ps` | 35000 | ps | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Table 11-3, p.59 | ACT to PRE. |
| `tRRD_ps` | 7500 | ps | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Table 11-3, p.59 | ACT to ACT, different banks. |
| `tWR_ps` | 15000 | ps | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Table 11-3, p.59 | Write recovery before PRE. |
| `tREFI_fst_ps` | 100000 | ps | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Table 11-3 / Table 7-5 | Row period while the one-shot fast refresh state is running. Not a JEDEC command interval. |
| `tREFI_lp_ps` | 3200000 | ps | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Table 7-5, p.52 | Low-power refresh period. Four banks at this rate take on the order of 64 ms. |
| `retention_ps` | 64000000000 | ps | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Section 5, p.44 | 64 ms at Tc <= 85 C. 32 ms above 85 C is not the default. |
| `tRESET_ps` | 5000000 | ps | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Table 11-3, p.59 | tRESET minimum 5 us. |
| `tPWR_clock_ps` | 200000000 | ps | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Section 4, p.42 | CK stable at least 200 us with CS# and STB high before reset. |
| `tZQINIT_ps` | 2000000 | ps | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Table 11-3, p.60 | Initialization ZQ calibration. |
| `tPPD_idle_ck` | 4 | CK | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Table 11-3, p.59 | Parallel-command spacing from the idle (all-bank precharged) state. |
| `tPPD_act_ck` | 8 | CK | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Table 11-3, p.59 | Parallel-command spacing once any row is open. Multiples of 8. |
| `tMOD` | max(12 CK, 15 ns) | CK | specified | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Table 11-3, p.59 | MRS update delay. |
| `bc_encoding` | n_words = BC + 1 | words | inferred | Rev 1.4 Table 7-3 plus ETH timing FSM, Table 7-3, p.52; rpc_timing_fsm.sv | The table lists BC 0..63. The minimum packet is 1 word, and the ETH countdown (BC<<3)+7 is 8 CK when BC=0. LiteDRAM documents the same +1. BC=0 therefore means one 32-byte word. |
| `tRTP` | end of read burst | CK | inferred | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), not listed in Table 11-3 | No tRTP number is published. PRE of the bank being read is refused until that read burst completes. |
| `addr_map` | byte[4:0] off, [10:5] col, [22:11] row, [24:23] bank | bits | inferred | ETH rpc_cmd_fsm.sv ACT/RD packing, controller address | Chosen so this model and the ETH controller select the same bank and row. The datasheet does not define a host address map. |
| `refresh_duration` | n_rows * tREFI * n_selected_banks | CK | inferred | Etron EM6GA16L 256Mb RPC DRAM Rev 1.4 (Oct 2024), Section 5, p.44-45 | One-shot refresh burst-refreshes every row of the selected banks, one row per tREFI, and the device is busy the whole time. |

## RPC DRAM at the ETH PHY clock

tCK = 5000 ps. ETH programs CL = 8 in MRS, so RL = WL = 9. The datasheet also permits CL = 3 at this frequency, but that is not the mode used by this controller trace. tRCD/tRP/tRAS/tRC/tRRD/tWR are the Table 11-3 nanosecond minimums rounded up to 5 ns. Active-state commands must also stay on the eight-CK grid: at 200 MHz, ACT to the first CAS is 8 CK even though tRCD is 3 CK. Peak pin bandwidth is 800 MB/s.
