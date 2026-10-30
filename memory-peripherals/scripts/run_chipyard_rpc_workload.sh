#!/usr/bin/env bash
# Run the bank-check workload on an already built Chipyard FireSim Verilator target.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
case "${1:-}" in
  rocket) TARGET=FireSimRocketConfig; TRACE=WithRpcDramRequestTrace_ ;;
  boom) TARGET=FireSimLargeBoomConfig; TRACE= ;;
  *) echo "Usage: $0 rocket|boom" >&2; exit 2 ;;
esac
GEN="$ROOT/third_party/chipyard-rocket/sims/firesim/sim/generated-src/f1/f1-midasexamples-FireSim-${TARGET}-${TRACE}RpcDram256Mb_BaseF1Config"
test -x "$GEN/VFireSim" || { echo "Build $GEN/VFireSim first" >&2; exit 1; }
mapfile -t RPC_ARGS < <(sed 's/=/_0=/' "$ROOT/configs/rpcdram-200-closed.conf")
mkdir -p "$ROOT/results/logs"
cd "$GEN"
./VFireSim +permissive +fesvr-step-size=128 +max-cycles=50000 \
  "${RPC_ARGS[@]}" +permissive-off "$ROOT/workloads/rpc_banks.riscv" \
  > "$ROOT/results/logs/${1}_rpc_stdout.log" \
  2> "$ROOT/results/logs/${1}_rpc_target.out"
rg -q '\*\*\* PASSED \*\*\*' "$ROOT/results/logs/${1}_rpc_target.out"
rg '\*\*\* PASSED \*\*\*' "$ROOT/results/logs/${1}_rpc_target.out"
