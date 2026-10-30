#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERILATOR_BIN="${VERILATOR_BIN:-}"
if [[ -z "$VERILATOR_BIN" ]]; then
  VERILATOR_BIN="$(command -v verilator || true)"
fi
if [[ -z "$VERILATOR_BIN" && -x /scratch/trazzaque/tools/miniforge/envs/fsim/bin/verilator ]]; then
  VERILATOR_BIN=/scratch/trazzaque/tools/miniforge/envs/fsim/bin/verilator
fi
[[ -n "$VERILATOR_BIN" ]] || { echo "Set VERILATOR_BIN to a Verilator executable" >&2; exit 2; }

mkdir -p results/logs
"$VERILATOR_BIN" --binary --timing -Wno-fatal \
  --top-module tb_hyperram_pin --Mdir rtl/obj_hyper_pin \
  rtl/hyperram_pin_memory.sv rtl/tb_hyperram_pin.sv \
  > results/logs/hyperram_pin_build.log 2>&1
./rtl/obj_hyper_pin/Vtb_hyperram_pin > results/logs/hyperram_pin_run.log 2>&1
rg -q '^PASS hyperram pin' results/logs/hyperram_pin_run.log

"$VERILATOR_BIN" --binary --timing -Wno-fatal \
  --top-module tb_rpc_timing_observe --Mdir rtl/obj_rpc_observer \
  rtl/rpc_timing_observe.sv rtl/tb_rpc_timing_observe.sv \
  > results/logs/rpc_observer_build.log 2>&1
./rtl/obj_rpc_observer/Vtb_rpc_timing_observe \
  > results/logs/rpc_observer_run.log 2>&1
rg -q '^PASS rpc observer' results/logs/rpc_observer_run.log

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x .venv/bin/python ]]; then PYTHON_BIN=.venv/bin/python; else PYTHON_BIN=python3; fi
fi
"$PYTHON_BIN" -m pytest -q \
  tests/test_calibration_and_eval.py tests/test_hyperram.py tests/test_rpcdram.py \
  independent/rpc_fased/tests \
  > results/logs/spec_python_run.log 2>&1

if [[ "${1:-}" == "--with-eth" ]]; then
  ./scripts/setup_eth_deps.sh > results/logs/spec_eth_deps.log 2>&1
  ./scripts/run_eth_timing_directed.sh > results/logs/spec_eth_run.log 2>&1
fi

echo "PASS standalone HyperRAM/RPC SV and Python checks"
if [[ "${1:-}" == "--with-eth" ]]; then echo "PASS ETH directed refresh checks"; fi
