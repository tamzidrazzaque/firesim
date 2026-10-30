#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source /scratch/trazzaque/tools/miniforge/etc/profile.d/conda.sh
conda activate fsim
verilator --binary --timing -DSYNTHESIS -Wno-fatal \
  -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -Wno-UNOPTFLAT \
  -Ithird_party/axi/include -Ithird_party/common_cells/include \
  -Ithird_party/register_interface/include \
  -y third_party/common_cells/src -y third_party/common_cells/src/deprecated \
  -y third_party/axi/src -y third_party/tech_cells_generic/src/rtl \
  -y third_party/rpc_dram_controller/src \
  -y third_party/rpc_dram_controller/src/interface_src \
  -y third_party/rpc_dram_controller/src/controller_src \
  -y third_party/rpc_dram_controller/src/controller_src/config_manager \
  -y third_party/rpc_dram_controller/src/controller_src/rpc_dram_phy \
  --top-module tb_eth_full_pin --Mdir rtl/obj_eth_full_pin -o Vtb_eth_full_pin \
  third_party/common_cells/src/cf_math_pkg.sv \
  third_party/axi/src/axi_pkg.sv \
  third_party/rpc_dram_controller/src/controller_src/rpc_dram_phy/rpc_cmd_pkg.sv \
  third_party/rpc_dram_controller/src/controller_src/rpc_config_path_pkg.sv \
  third_party/rpc_dram_controller/src/rpc_ctrl_pkg.sv \
  third_party/tech_cells_generic/src/rtl/tc_clk.sv \
  third_party/rpc_dram_controller/src/controller_src/rpc_dram_phy/generic_delay_D5_O1_5P000_CG0.behav.sv \
  rtl/rpc_pin_memory.sv rtl/tb_eth_full_pin.sv \
  > results/logs/eth_full_pin_build.log 2>&1
./rtl/obj_eth_full_pin/Vtb_eth_full_pin > results/logs/eth_full_pin_run.log 2>&1
tail -20 results/logs/eth_full_pin_run.log
