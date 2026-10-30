#!/bin/bash
# Re-run the Python suite, the Verilator device tests, and the characterization.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source /scratch/trazzaque/tools/miniforge/etc/profile.d/conda.sh
conda activate fsim
cd "$ROOT"
mkdir -p results/logs
.venv/bin/python -m pytest tests -q --tb=short | tee results/logs/pytest.txt

cd "$ROOT/rtl"
verilator --binary --timing -Wno-fatal -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -Wno-BLKANDNBLK \
  --top-module tb_hyperram_txn -o Vtb_hyperram --Mdir obj_hyper \
  tb_hyperram_txn.sv hyperram_txn.sv
./obj_hyper/Vtb_hyperram | tee "$ROOT/results/logs/rtl_hyperram.txt"

verilator --binary --timing -Wno-fatal -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -Wno-BLKANDNBLK \
  --top-module tb_rpc_array -o Vtb_rpc --Mdir obj_rpc \
  tb_rpc_array.sv rpc_array.sv
./obj_rpc/Vtb_rpc | tee "$ROOT/results/logs/rtl_rpc.txt"

verilator --binary --timing -Wno-fatal -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC \
  --top-module tb_eth_cmd_decoder -o Vtb_eth --Mdir obj_eth \
  tb_eth_cmd_decoder.sv \
  "$ROOT/third_party/rpc_dram_controller/src/controller_src/rpc_dram_phy/rpc_cmd_pkg.sv" \
  "$ROOT/third_party/rpc_dram_controller/src/controller_src/rpc_dram_phy/rpc_cmd_decoder.sv"
./obj_eth/Vtb_eth | tee "$ROOT/results/logs/rtl_eth_decoder.txt"

cd "$ROOT"
.venv/bin/python scripts/characterize.py | tee results/logs/characterize.txt
echo "logs in $ROOT/results/logs"
