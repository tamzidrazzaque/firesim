#!/usr/bin/env bash
# Fetch the controller's declared Bender dependencies into this project only.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p third_party
clone_tag() {
  local name="$1" tag="$2"
  if [[ ! -d "third_party/$name/.git" ]]; then
    git clone --depth 1 --branch "$tag" "https://github.com/pulp-platform/$name.git" "third_party/$name"
  fi
}
clone_tag common_cells v1.21.0
clone_tag axi v0.35.0
clone_tag register_interface v0.3.1
clone_tag tech_cells_generic v0.2.9
if [[ ! -d third_party/rpc_dram_controller/.git ]]; then
  git clone https://github.com/pulp-platform/rpc_dram_controller.git third_party/rpc_dram_controller
  git -C third_party/rpc_dram_controller checkout 3ce56547
fi
for entry in \
  'third_party/tech_cells_generic patches/tech_cells_generic_verilator_5_022.patch' \
  'third_party/rpc_dram_controller patches/eth_rpc_cmd_fsm_act_addr.patch'; do
  read -r repo patch_file <<< "$entry"
  if git -C "$repo" apply --check "$ROOT/$patch_file" 2>/dev/null; then
    git -C "$repo" apply "$ROOT/$patch_file"
  fi
done
echo 'ETH dependencies ready in third_party/'
