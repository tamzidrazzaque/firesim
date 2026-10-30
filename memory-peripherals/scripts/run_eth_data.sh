#!/usr/bin/env bash
# Build and run the ETH AXI-interface + command-FSM directed data test.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source /scratch/trazzaque/tools/miniforge/etc/profile.d/conda.sh
conda activate fsim
mkdir -p results/logs
verilator --binary --timing -DSYNTHESIS -Wno-fatal \
  -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -Wno-UNOPTFLAT \
  -Ithird_party/axi/include -Ithird_party/common_cells/include \
  -Ithird_party/register_interface/include \
  -y third_party/common_cells/src -y third_party/common_cells/src/deprecated \
  -y third_party/axi/src -y third_party/tech_cells_generic/src/rtl \
  --top-module tb_eth_interface_data --Mdir rtl/obj_eth_data -o Vtb_eth_data \
  third_party/common_cells/src/cf_math_pkg.sv \
  third_party/axi/src/axi_pkg.sv \
  third_party/rpc_dram_controller/src/controller_src/rpc_dram_phy/rpc_cmd_pkg.sv \
  third_party/rpc_dram_controller/src/controller_src/rpc_config_path_pkg.sv \
  third_party/rpc_dram_controller/src/rpc_ctrl_pkg.sv \
  rtl/tb_eth_interface_data.sv \
  third_party/rpc_dram_controller/src/interface_src/*.sv \
  third_party/rpc_dram_controller/src/controller_src/rpc_dram_phy/rpc_cmd_fsm.sv \
  > results/logs/eth_interface_build.log 2>&1
./rtl/obj_eth_data/Vtb_eth_data | tee results/logs/eth_interface_data.log
rg -q '^PASS ETH AXI interface and command FSM data path$' results/logs/eth_interface_data.log
