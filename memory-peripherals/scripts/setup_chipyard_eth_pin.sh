#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CY="$ROOT/third_party/chipyard-rocket"
[[ -e "$CY/.git" ]] || { echo "Chipyard checkout missing at $CY" >&2; exit 1; }
copy_if_changed() {
  local source="$1" target="$2"
  mkdir -p "$(dirname "$target")"
  if ! cmp -s "$source" "$target"; then cp "$source" "$target"; fi
}
copy_if_changed "$ROOT/integration/chipyard/RpcHarness.scala" "$CY/generators/chipyard/src/main/scala/harness/RpcHarness.scala"
copy_if_changed "$ROOT/integration/chipyard/RpcConfigs.scala" "$CY/generators/chipyard/src/main/scala/config/RpcConfigs.scala"
copy_if_changed "$ROOT/integration/chipyard/SimRPC.v" "$CY/generators/chipyard/src/main/resources/chipyard/vsrc/SimRPC.v"
for config in RpcRocketConfig RpcBoomConfig; do
  generated="$CY/sims/verilator/generated-src/chipyard.harness.TestHarness.$config/gen-collateral/SimRPC.v"
  if [[ -f "$generated" ]]; then copy_if_changed "$ROOT/integration/chipyard/SimRPC.v" "$generated"; fi
done
if [[ ! -f "$CY/tools/DRAMSim2/Makefile" ]]; then
  git -C "$CY" submodule update --init tools/DRAMSim2
fi
