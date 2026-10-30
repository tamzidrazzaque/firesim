#!/usr/bin/env bash
# Rocket or BOOM through the ETH controller, pin memory, and the online
# timing observer. Logs are separate from the 2026-10-23 pin-path runs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
"$ROOT/scripts/setup_chipyard_eth_pin.sh"
source /scratch/trazzaque/tools/miniforge/etc/profile.d/conda.sh
conda activate fsim
export RISCV=/scratch/trazzaque/tools/riscv
export PATH="/scratch/trazzaque/tools/firtool-1.75.0/bin:$RISCV/bin:$PATH"
export JAVA_TOOL_OPTIONS='-Xmx32G -Xss8M -Djava.io.tmpdir=/scratch/trazzaque/tmp'
case "${1:-}" in
  rocket) CONFIG=RpcRocketConfig ;;
  boom) CONFIG=RpcBoomConfig ;;
  *) echo "Usage: $0 rocket|boom" >&2; exit 2 ;;
esac
CY="$ROOT/third_party/chipyard-rocket"
ETH="$ROOT/third_party/rpc_dram_controller/src"
EXTRA="+define+SYNTHESIS -y $ROOT/third_party/common_cells/src -y $ROOT/third_party/common_cells/src/deprecated -y $ROOT/third_party/axi/src -y $ROOT/third_party/tech_cells_generic/src/rtl -y $ETH -y $ETH/interface_src -y $ETH/controller_src -y $ETH/controller_src/config_manager -y $ETH/controller_src/rpc_dram_phy $ROOT/third_party/common_cells/src/cf_math_pkg.sv $ROOT/third_party/axi/src/axi_pkg.sv $ETH/controller_src/rpc_dram_phy/rpc_cmd_pkg.sv $ETH/controller_src/rpc_config_path_pkg.sv $ETH/rpc_ctrl_pkg.sv $ROOT/third_party/tech_cells_generic/src/rtl/tc_clk.sv $ETH/controller_src/rpc_dram_phy/generic_delay_D5_O1_5P000_CG0.behav.sv $ROOT/rtl/rpc_pin_memory.sv $ROOT/rtl/rpc_timing_observe.sv"
INCS="$ROOT/third_party/axi/include $ROOT/third_party/common_cells/include $ROOT/third_party/register_interface/include"
mkdir -p results/logs
make -C "$CY/sims/verilator" CONFIG="$CONFIG" EXT_INCDIRS="$INCS" EXTRA_SIM_SOURCES="$EXTRA" EXTRA_SIM_REQS="$ROOT/rtl/rpc_pin_memory.sv $ROOT/rtl/rpc_timing_observe.sv $ROOT/integration/chipyard/SimRPC.v" VERILATOR_THREADS=4 > "results/logs/chipyard_eth_timing_${1}_build.log" 2>&1
SIM="$CY/sims/verilator/simulator-chipyard.harness-$CONFIG"
cd "$CY/sims/verilator"
"$SIM" +permissive +max-cycles=2000000 +permissive-off "$ROOT/workloads/rpc_banks.riscv" > "$ROOT/results/logs/chipyard_eth_timing_${1}_stdout.log" 2> "$ROOT/results/logs/chipyard_eth_timing_${1}_target.out"
rg -q 'TestDriver.v:158: Verilog \$finish' "$ROOT/results/logs/chipyard_eth_timing_${1}_stdout.log"
echo "PASS ${1}: TestDriver success branch with timing observer"
