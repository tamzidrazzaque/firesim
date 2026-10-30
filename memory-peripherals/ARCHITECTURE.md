# Architecture

Two layers share one parameter set.

1. **Device / protocol model.** Consumes the operations a controller actually issues. HyperRAM consumes a HyperBus transaction (command/address, latency, byte stream, RWDS mask). RPC DRAM consumes ACT, PRE, RD, WR, REF, MRS, ZQC, and BST, and checks them against the datasheet spacing rules. This is what a controller candidate should be graded against.
2. **FASED transaction model.** Consumes AXI bursts and turns them into whatever the device needs, then reports when the response is due. This is what a Chipyard SoC should be simulated against. It does not prove that a PHY's pin timing is correct.

The HBM model already in FireSim (`HBMModel`, branch `hbm-arch1-compact-test`, `8ce47277f`) stays the pattern for layer 2: one AXI port, runtime-programmable timings, optional request trace, functional bytes elsewhere. HyperRAM and RPC DRAM do not reuse its bank-group scheduler. HyperRAM has no host-visible banks. RPC DRAM has four banks and a single multiplexed command/data bus, not HBM's split row and column buses.

## HyperRAM

Target: Infineon S80KS2562, 256 Mbit, 1.8 V, 200 MHz grade. The exact [Rev. *C datasheet](https://www.infineon.com/dgdl/Infineon-S80KS2562_1.8_V_256-Mb_HyperBus_Interface_HyperRAM_%28Self-Refresh_DRAM%29-DataSheet-v01_00-EN.pdf?fileId=8ac78c8c7dc4255f017dd82db3d308ae) is available. Values and assumptions are tagged in `docs/parameters.md`; the SV handoff scope is in `docs/SV_VERIFICATION_HANDOFF.md`.

A transaction is 3 CK of command/address, then L or 2L CK of initial latency, then one byte per edge (2 bytes per CK). Power-on CR0 is `0x8F2F`: latency code 7, fixed latency, 32-byte legacy wrap. CR0[3] = 0 selects variable latency. RWDS high during the command phase means the access collided with an internal refresh and the latency doubles. RWDS high on a write byte masks that byte.

Refresh is not a command. The datasheet sets the maximum interval between adjacent internal refreshes equal to tCSM: 4 µs at or below 85 °C, 1 µs above. The Python performance model chooses reset as a deterministic internal phase, accrues one due refresh per tCSM, and retires one during a CS# high gap of at least tRFH (35 ns). That phase is an assumption. The SV pin model instead exposes a `force_refresh_collision_i` input so both 1x and 2x variable latency can be tested without assuming a hidden phase. The FASED scheduler splits long AXI bursts to keep each chip-select below tCSM. The exact datasheet specifies 1 KiB rows.

Reset is tRP (200 ns) low and tRH (200 ns) high before the first chip-select. Deep power-down is CR0[15] = 0 and blocks memory traffic until reset.

## RPC DRAM

Target: Etron EM6GA16L, 256 Mbit, x16, Rev 1.4. Four banks, 4096 rows, 2 KB pages. One "word" is 16 beats on the 16-bit DDR bus, 32 bytes, and it takes 8 CK. The burst-count field is `n_words - 1`. The datasheet table lists the field as 0..63; BC = 0 is one word. That reading matches the ETH timing FSM, whose countdown is `(burst_length << 3) + 7`, and the LiteDRAM comment that the count is plus one.

RL = WL = CL + 1 because AL is fixed at 1. Speed-1600 uses CL = 11, so RL = 12, tCK = 1.25 ns. The ETH PHY is clocked at 200 MHz (`PHY_CLOCK_PERIOD = 5`) and sends an MRS packet selecting CL = 8, so its actual RL is 9. Active-state tPPD is 8 CK, larger than tRCD (3 CK), and limits the first column command after an activate.

The host address map matches `rpc_cmd_fsm.sv`, not a map from the datasheet (the datasheet does not define one):

| Bits | Field |
|---|---|
| `[4:0]` | byte inside the 32-byte word |
| `[10:5]` | column group (CA[9:4]) |
| `[22:11]` | row |
| `[24:23]` | bank |

Parallel commands are illegal while a burst is open, except by ending the burst. Serial commands sit on an 8 CK grid measured from the parallel command that opened the burst. The open-page scheduler uses that path so consecutive reads of an open row keep the data bus full. Closed page matches the ETH command FSM, which precharges after every read or write.

Refresh is a command, not a background timer. Section 5 describes one-shot refresh as a pass over the selected banks with a 100 ns fast-refresh step, but does not give a named `tRFC` or exact exit cycle. The row-step implementation uses 4096 rows × selected banks × tREFI; four banks at speed-1600 is 1,310,720 CK (1.638 ms). This is an explicit interpretation pending vendor confirmation. Low-power refresh uses a 3.2 µs step and is a separate mode.

## What talks to what

```
AXI target
    |
    +-- Chisel HyperRAMModel / RpcDramModel   (FireSim, timing only)
    |
    +-- Python HyperRAMFased / RpcDramFased   (workload timing + data)
            |
            +-- HyperRAMDevice / RpcDramDevice (protocol checks + array)
                    ^
                    |
            evaluate.py  <--- command trace from a controller
            rtl/rpc_array, hyperram_txn, ETH rpc_cmd_decoder
```

`evaluate.py` is the hook for a later agent. It accepts a JSON command list, replays it, and returns violations. `safe_probe_plan()` is a short list of legal reads and one legal activate/read. It is not permission to invent pin waveforms on a board.

## What this does not model

- DQ/RWDS/DQS analog timing, ODT, ZQ resistor sharing, or board skew.
- HyperRAM differential clock and analog pad timing. The exact datasheet confirms ID0 = `0x0E86`.
- RPC serial utility commands beyond BST, pipelined activate is implemented in the Python scheduler but not in the Chisel FSM.
- The ETH PHY and full AXI-to-RPC path now run against a digital pin memory in `rtl/rpc_pin_memory.sv`, including Rocket and BOOM Chipyard workloads. Analog PHY behavior, board timing, long-run refresh, and full datasheet timing coverage remain outside that model.
- HBM itself. The existing model was not modified. The 38.4 GB/s figure in the CSV is the published one-channel pin ceiling, included only as scale.
