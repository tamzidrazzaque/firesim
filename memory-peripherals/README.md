# Memory peripherals

This directory lives on the `memory-peripherals` branch of
`tamzidrazzaque/firesim`. The SystemVerilog files for controller verification
are [`rtl/hyperram_pin_memory.sv`](rtl/hyperram_pin_memory.sv),
[`rtl/rpc_pin_memory.sv`](rtl/rpc_pin_memory.sv), and
[`rtl/rpc_timing_observe.sv`](rtl/rpc_timing_observe.sv). Read
[`docs/SV_VERIFICATION_HANDOFF.md`](docs/SV_VERIFICATION_HANDOFF.md) for the
supported modes and timing assumptions before writing tests.

FireSim-oriented models of HyperRAM and RPC DRAM for the SLICE external-memory project. A separate Chipyard Verilator harness connects Rocket or BOOM through ETH RPC controller RTL to a digital pin-side RPC memory model.

The Python package in `src/memperiph` models functional data and transaction timing. `independent/rpc_fased/` is a separate command-level RPC checker. The digital pin models and RPC timing observer in `rtl/` are the controller verification entry points; their exact scope and limitations are in [the SV handoff](docs/SV_VERIFICATION_HANDOFF.md). A thinner Chisel timing model in `fased/` plugs into the existing FASED AXI bridge. It times requests while FASED functional memory stores the bytes.

These are simulated timings. Nothing in this tree was run on the U250, and no XDMA, JTAG, or FPGA programming interface was opened.

## Layout

| Path | What it is |
|---|---|
| `src/memperiph/` | HyperRAM device, RPC DRAM device, FASED-style schedulers, calibration, trace harness |
| `tests/` | Pytest suite. Asserts expected data and cycle counts |
| `fased/` | Chisel sources and the config fragments applied onto an isolated FireSim checkout |
| `configs/` | Runtime plusarg files for the Chisel models |
| `rtl/` | HyperRAM digital pin model, RPC pin memory and timing observer, and Verilator testbenches |
| `integration/chipyard/` | Rocket/BOOM harness that routes AXI through the ETH controller to the RPC pin model |
| `independent/rpc_fased/` | Datasheet-derived RPC command checker and negative timing tests |
| `third_party/firesim` | Isolated FireSim checkout at `8ce47277f` (`hbm-arch1-compact-test`), with the new models applied |
| `third_party/rpc_dram_controller` | Isolated ETH Zurich controller `3ce56547`, with the documented ACT-address patch applied locally |
| `docs/parameters.md` | Timing constants, source, and specified/inferred/approximation tag |
| `docs/SV_VERIFICATION_HANDOFF.md` | Exact parts, supported SV modes, tests, and open spec interpretations |
| `docs/VALIDATION_2026-10-30.md` | Current status matrix, same-clock FASED/ETH comparison, and research limits |
| `results/` | Pytest log, characterization CSV, plots |

`schwarz-em/hyperram-phy-secret` is not visible with the current GitHub credentials. No vendor Verilog model is copied into this tree.

## Run the tests

```bash
cd memory-peripherals
./scripts/run_sv_spec_checks.sh --with-eth
./scripts/run_chipyard_eth_timing.sh rocket
./scripts/run_chipyard_eth_timing.sh boom
.venv/bin/python scripts/verify_rpc_trace_evidence.py
```

Python only:

```bash
cd memory-peripherals
.venv/bin/python -m pytest -q tests/test_calibration_and_eval.py tests/test_hyperram.py tests/test_rpcdram.py independent/rpc_fased/tests
.venv/bin/python scripts/characterize.py
```

The characterization script writes `results/characterization/performance.csv` and two plots. Bandwidths are memory-clock cycles times the programmed tCK. They are not wall-clock simulation rates or silicon measurements. The SV handoff explains why passing these workloads is not full device signoff.

## FireSim

```bash
./scripts/apply_fased.sh
cd third_party/firesim/sim
# conda env fsim, FIRESIM_ENV_SOURCED=1, SBT_OPTS pointed at this checkout
sbt -batch "project midas" compile
```

Fuzzer configs, once that compile is used by a metasim build:

- `PLATFORM_CONFIG=HyperRAMF2Config` or `HyperRAMF2ReqTraceConfig`
- `PLATFORM_CONFIG=RpcDramF2Config` or `RpcDramF2ReqTraceConfig`

Plusargs are the files in `configs/`. The FASED driver wants the model index before the equals sign (`+mm_tLAT_0=7`). `sim/scripts/hbm-validation/run_hbm_validation.sh` already does that rewrite.

The AXI fuzzer metasim was run for both models. Each accepted 10,000 requests and exited 0. Commands and traces are in `TESTING.md`.
