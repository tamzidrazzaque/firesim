#!/bin/bash
# Copy the memory models into the isolated FireSim worktree.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FS="$ROOT/third_party/firesim"
DRAM="$FS/sim/midas/src/main/scala/midas/models/dram"
CFG="$FS/sim/midas/src/main/scala/configs/FASEDTargetConfigs.scala"
TEST="$FS/sim/src/main/scala/fasedtests/Config.scala"
cp "$ROOT/fased/scala/midas/models/dram/HyperRAMModel.scala" "$DRAM/"
cp "$ROOT/fased/scala/midas/models/dram/RpcDramModel.scala" "$DRAM/"
cp "$ROOT/fased/scala/midas/models/dram/IndRpcDramModel.scala" "$DRAM/"
if ! grep -q "class WithHyperRAM" "$CFG"; then
  cat "$ROOT/fased/config/FASEDTargetConfigs.append.scala" >> "$CFG"
fi
if ! grep -q "class WithIndRpcDram" "$CFG"; then
  cat >> "$CFG" << 'EOF'

class WithIndRpcDram
    extends Config((site, _, _) => { case MemModelKey =>
      new IndRpcDramModelConfig(
        params       = site(BaseParamsKey),
        requestTrace = false,
      )
    })

class WithIndRpcDramRequestTrace
    extends Config((_, _, up) => { case MemModelKey =>
      up(MemModelKey) match {
        case model: IndRpcDramModelConfig => model.copy(requestTrace = true)
        case other                        =>
          throw new IllegalArgumentException(
            s"WithIndRpcDramRequestTrace requires an IndRpcDramModelConfig, got: ${other.getClass.getName}"
          )
      }
    })

class IndRpcDram256Mb
    extends Config(
      new WithFuncModelLimits(32, 32) ++
        new WithIndRpcDram ++
        new WithDefaultMemModel
    )
EOF
fi
if ! grep -q "class HyperRAMF2Config" "$TEST"; then
  cat "$ROOT/fased/config/fasedtests.append.scala" >> "$TEST"
fi
if ! grep -q "class IndRpcDramF2Config" "$TEST"; then
  cat >> "$TEST" << 'EOF'

class IndRpcDramF2Config
    extends Config(
      new IndRpcDram256Mb ++
        new midas.F2Config
    )

class IndRpcDramF2ReqTraceConfig
    extends Config(
      new WithIndRpcDramRequestTrace ++
        new IndRpcDramF2Config
    )
EOF
fi
mkdir -p "$FS/sim/custom-runtime-configs"
cp "$ROOT/configs/"*.conf "$FS/sim/custom-runtime-configs/"
sha="$(git -C "$FS" rev-parse --short HEAD 2>/dev/null || true)"
echo "applied models onto ${sha:-no-commit}"
