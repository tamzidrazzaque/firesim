# SV verification handoff: HyperRAM and RPC DRAM

The latest layer-by-layer validation status is in
`VALIDATION_2026-10-30.md`. For an additional independent timing check of
the observed ETH commands, run
`.venv/bin/python scripts/verify_rpc_trace_evidence.py` after producing the
pin logs. It exports raw packet and original-cycle JSONL traces for a second
implementation to consume. The FASED scheduler files are under
`fased/scala/midas/models/dram/`; they schedule AXI requests and are not
drop-in SV pin devices.

This repository provides **digital simulation models for the supported modes**,
not a full electrical or all-mode vendor signoff model. Use the exact part and
mode below when comparing a controller against them. Keep the timing observer
enabled alongside the RPC pin memory: the memory checks transfer data and REF
BUSY signaling, while the observer rejects illegal command timing.

## Parts, specifications, and scope

| Device | Exact source | Mode exercised |
|---|---|---|
| HyperRAM | [Infineon S80KS2562 Rev. *C, 256 Mb, 1.8 V](https://www.infineon.com/dgdl/Infineon-S80KS2562_1.8_V_256-Mb_HyperBus_Interface_HyperRAM_%28Self-Refresh_DRAM%29-DataSheet-v01_00-EN.pdf?fileId=8ac78c8c7dc4255f017dd82db3d308ae) | 200 MHz, normal operation, default fixed L=7 plus variable 1×/2× latency, CR0/CR1, 32 MiB array |
| RPC DRAM | [Etron EM6GA16L Rev. 1.4](https://etron.com/wp-content/uploads/2022/04/EM6GA16LGDBXCAEA-RPC1-DRAM-Induatrial_Rev.-1.4.pdf) | 200 MHz ETH controller, CL=8, AL=1, RL=WL=9; separate Python speed-1600 CL=11 checker |

`rtl/hyperram_pin_memory.sv` accepts separate host DQ/RWDS values and output
enables and drives device values and output enables. It checks the 48-bit DDR
CA, latency, register writes, RWDS collision indication, write masks, linear
and wrapped bursts, array wrap, CS# gaps, read-to-write recovery, reset, and
maximum CS# low. `force_refresh_collision_i` selects a collision for directed
tests. The silicon's internal refresh phase is unpublished and cannot be
predicted from a deterministic testbench counter. The model does not apply a
retention-failure policy to stored bytes.

`rtl/rpc_pin_memory.sv` accepts the ETH DB/DQS/STB packet pins, stores 32-byte
words in four banks, applies first/last word byte masks, and returns read data.
Its `dqs_oe_o` is the digital drive enable: during one-shot REF BUSY both DQS
outputs are high, then both pulse low for `TRFQSL_CK`, then release. Existing
Chipyard tests consume the values directly; a pad-level testbench should use
the drive enable. `rtl/rpc_timing_observe.sv` watches the same command pins and
reports the offered cycle and earliest legal cycle. Set
`FATAL_ON_VIOLATION=1` and `FATAL_ON_REFRESH_BUSY=1` for a controller test. The
Chipyard harness does both. The observer rejects an early command without
advancing its bank or refresh state.

## Timing choices that must be visible in a verification plan

| Rule | Source and implemented interpretation |
|---|---|
| HyperRAM refresh | Rev. *C section 6.3.2: maximum interval between internal refreshes equals tCSM, 4 µs through 85 °C or 1 µs above. Fixed latency is always 2L; variable latency is 1L or 2L from RWDS during CA. The pin model exposes collision injection because internal phase is not published. |
| HyperRAM row and capacity | Rev. *C Table 5 and section 6.2.1: 512 words per 1 KiB row; 16 Mi 16-bit words total. Linear bursts wrap at the array end. |
| RPC active command grid | Rev. 1.4 section 2.8 and Table 11-3: intervals between parallel commands in the activate state are 8 CK or integer multiples. The 11-CK speed-1600 tRCD therefore permits the first CAS at ACT+16. The ETH 5 ns tRCD is 3 CK, but its first legal CAS is ACT+8; actual traces use ACT+16. |
| RPC refresh | Rev. 1.4 section 5.1: one-shot REF precharges all banks, refreshes the selected banks, and blocks commands while BUSY. It does not publish a `tRFC` or exact one-shot completion cycle. `REFRESH_ROW_STEP=1` interprets the duration as 4096 rows × tREFI × selected banks; `=0` uses one tREFI. **Neither duration is vendor-confirmed.** The directed ETH and Chipyard harnesses use the row-step choice. |
| RPC high temperature | Section 5 limits LP REF to one or two banks above 85 °C. Set `CASE_TEMP_GT85=1` in both RPC modules for that condition. |

All RPC nanosecond minima, their cycle conversions, and the chosen host
address map are catalogued in `docs/parameters.md`. The host address map is
the ETH controller's map; the Etron datasheet does not specify one. The
independent Python checker and its tests are under `independent/rpc_fased/`.

## Reproduce the checks

From the project root:

```bash
./scripts/run_sv_spec_checks.sh --with-eth
./scripts/run_chipyard_eth_timing.sh rocket
./scripts/run_chipyard_eth_timing.sh boom
```

The first script builds and runs `tb_hyperram_pin`,
`tb_rpc_timing_observe`, the Python checks, and the directed production ETH
controller test. The HyperRAM bench checks fixed and variable latency,
injected refresh collision, masks, register access, exact/early tCSHI and
tRWR, early tRP/tRH/tCSS, array wrap, and tCSM overrun. The RPC observer bench checks startup,
minimum and off-grid tPPD, REF versus tRC and read-data end, rejected-state
preservation, reserved MRS, BUSY end, high-temperature LP bank limit, and
empty bank mask. The directed ETH test checks 1-, 2-, and 4-bank refresh,
BUSY strobes, readback, AXI read backpressure, an intentional too-short REF
setting, and an intermediate REF wait that separates the two documented
refresh interpretations. Rocket and
BOOM run `workloads/rpc_banks.riscv` through the ETH controller and digital
RPC model, with the observer set to fatal on violations. Logs go under
`results/logs/`; they are generated evidence, not part of the source commit.
The latest runs reached the workload success branch with zero observer
violations: Rocket emitted 394 pin commands and BOOM 409, both across banks
0–3. The directed ETH run read data back after 1-, 2-, and 4-bank REF and
the intentionally underprogrammed negative run reported one `tREFI` violation
under both readings. The intermediate wait was accepted under one-tREFI and
rejected under row-step; only a device waveform can settle its actual legality.
The standalone models need Verilator and Python. The ETH runs use the isolated
controller checkout at `3ce565470a60e171965a1bc94ce5b0a61c2003a6`;
`scripts/setup_eth_deps.sh` fetches its declared public dependencies and
applies the local ACT address patch. The core runs also require the isolated
Chipyard checkout at `0b1bf0019164b94e67826ec0deed9e29a69d7e39` in
`third_party/chipyard-rocket`; `scripts/setup_chipyard_eth_pin.sh` installs
the harness files there. These checkouts are outside the source commit.

## Limits for the next SV verification pass

- RPC normal **parallel one-shot** mode is the supported pin-model path.
  The pin data model is tied to the ETH 200 MHz CL=8 configuration. Its
  parameterized observer and the Python checker cover other clock profiles,
  but the pin data timing has not been validated at speed-1600.
  Serial streaming/utility packets, loop refresh, power-down, deep power-down,
  training, all MRS variations, and analog DB/DQS setup, hold, skew, and
  termination are not modeled to signoff fidelity.
- HyperRAM hybrid sleep and deep power-down are flagged as unsupported, and
  electrical pad timings, VCC ramp, and actual retention loss are absent.
  `force_refresh_collision_i` is a test control, not a silicon refresh clock.
- The row-step REF occupancy and one-tREFI alternative require a device
  waveform or vendor clarification before claiming a unique timing contract.
  The model intentionally exposes both. Long-running Rocket/BOOM workloads
  here do not cause REF on their own; directed tests issue REF explicitly.
- FireSim FASED Chisel models are AXI performance schedulers. They cannot
  independently prove an external PHY/controller pin protocol. Use the SV
  pin models and observer for that verification.
