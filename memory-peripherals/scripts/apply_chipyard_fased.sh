#!/usr/bin/env bash
# Install the existing HyperRAM/RPC FASED sources in an isolated Chipyard copy.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CY="$ROOT/third_party/chipyard-rocket"
DRAM="$CY/sims/firesim/sim/midas/src/main/scala/midas/models/dram"
CFG="$CY/sims/firesim/sim/midas/src/main/scala/configs/FASEDTargetConfigs.scala"
test -d "$DRAM" || { echo "Missing isolated Chipyard copy: $CY" >&2; exit 1; }
cp "$ROOT/fased/scala/midas/models/dram/HyperRAMModel.scala" "$DRAM/"
cp "$ROOT/fased/scala/midas/models/dram/RpcDramModel.scala" "$DRAM/"
if ! rg -q 'class RpcDram256Mb' "$CFG"; then
  cat "$ROOT/fased/config/FASEDTargetConfigs.append.scala" >> "$CFG"
fi
FIRE_SIM="$CY/sims/firesim"
HEADER_PATCH="$ROOT/patches/chipyard_firesim_cstdint.patch"
if git -C "$FIRE_SIM" apply --check "$HEADER_PATCH" 2>/dev/null; then
  git -C "$FIRE_SIM" apply "$HEADER_PATCH"
fi
echo "Installed FASED memory models in $CY"
