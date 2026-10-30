"""Machine-readable evaluation of a controller command trace.

A later agent can propose transactions, run them through this harness, and
read the JSON result. Physical experiments must stay inside
``safe_probe_plan``: those are read-only or use the shortest legal writes
the datasheet allows. The harness does not generate arbitrary pin patterns.
"""

from __future__ import annotations

import json
from typing import Any

from .hyperram import REG_CR0, REG_ID0, HyperRAMDevice, HyperRAMParams
from .rpcdram import RpcCommand, RpcDramDevice, RpcDramParams
from .util import Violation


def _violation_dicts(violations) -> list[dict[str, Any]]:
    return [{"cycle": v.cycle, "code": v.code, "detail": v.detail} for v in violations]


def evaluate_rpc_trace(trace: list[dict[str, Any]], *,
                       params: RpcDramParams | None = None,
                       assume_initialized: bool = True) -> dict[str, Any]:
    """Replay decoded RPC commands. Each item needs ``op`` and ``cycle``."""
    dev = RpcDramDevice(params, assume_initialized=assume_initialized)
    for item in trace:
        fields = {k: v for k, v in item.items() if k != "why"}
        dev.issue(RpcCommand(**fields))
    return {
        "memory": "rpc-dram",
        "pass": not dev.violations,
        "n_commands": len(trace),
        "n_violations": len(dev.violations),
        "violations": _violation_dicts(dev.violations),
        "final_cycle": dev.cycle,
        "cl": dev.cl,
    }


def evaluate_hyperram_script(script: list[dict[str, Any]], *,
                             params: HyperRAMParams | None = None) -> dict[str, Any]:
    """Replay a host script of reset / wait / read / write operations.

    This is a transaction driver, not a pin-level controller.
    """
    dev = HyperRAMDevice(params)
    for step in script:
        op = step["op"]
        if op == "reset":
            dev.power_on_reset()
        elif op == "wait":
            dev.wait(int(step["cycles"]))
        elif op == "read":
            dev.read(int(step["addr"]), int(step["nbytes"]),
                     space=step.get("space", "mem"),
                     linear=step.get("linear", True),
                     obey_timing=step.get("obey_timing", True))
        elif op == "write":
            data = bytes.fromhex(step["data"])
            dev.write(int(step["addr"]), data, space=step.get("space", "mem"),
                      linear=step.get("linear", True),
                      obey_timing=step.get("obey_timing", True))
        else:
            dev.violations.append(Violation(dev.cycle, "script", f"unknown op {op}"))
    return {
        "memory": "hyperram",
        "pass": not dev.violations,
        "n_steps": len(script),
        "n_violations": len(dev.violations),
        "violations": _violation_dicts(dev.violations),
        "final_cycle": dev.cycle,
        "cr0": dev.cr0,
    }


def safe_probe_plan() -> dict[str, Any]:
    """Legal, read-mostly experiments for a future hardware loop.

    Nothing here holds CS# for longer than a short transfer, writes a
    destructive pattern over the whole device, or issues an undefined
    opcode. A physical runner still has to enforce board voltage and the
    part's absolute maximum ratings; this list is not an electrical permit.
    """
    return {
        "version": 1,
        "limits": {
            "hyperram_max_cs_low_ck": 64,
            "rpc_max_words_per_command": 4,
            "writes": "single 32-bit register or one 32-byte data word",
            "forbidden": ["undefined opcode", "CS# low beyond tCSM", "ZQ overlap", "tRCD violation"],
        },
        "hyperram": [
            {"op": "read", "addr": REG_ID0 * 2, "nbytes": 2, "space": "reg", "why": "read-only identification"},
            {"op": "read", "addr": REG_CR0 * 2, "nbytes": 2, "space": "reg", "why": "latency and burst configuration"},
            {"op": "read", "addr": 0, "nbytes": 2, "space": "mem", "why": "shortest memory read, captures RWDS latency"},
            {"op": "wait", "cycles": 2, "why": "minimum tCSHI gap"},
            {"op": "read", "addr": 0, "nbytes": 2, "space": "mem", "why": "back-to-back read after the minimum gap"},
            {"op": "wait", "cycles": 4000, "why": "idle long enough for one distributed refresh"},
            {"op": "read", "addr": 0, "nbytes": 2, "space": "mem", "why": "read after a refresh opportunity"},
        ],
        "rpc": [
            {"op": "ACT", "cycle": 0, "bank": 0, "row": 0, "why": "open one row"},
            {"op": "RD", "cycle": 16, "bank": 0, "row": 0, "col": 0, "bc": 0,
             "why": "one-word read at the first legal 8-CK slot after tRCD"},
            {"op": "BST", "cycle": 24, "serial": True, "why": "retire the burst on the serial grid"},
        ],
    }


def run_safe_probes(params_hyper: HyperRAMParams | None = None,
                    params_rpc: RpcDramParams | None = None) -> dict[str, Any]:
    plan = safe_probe_plan()
    hyper = evaluate_hyperram_script(plan["hyperram"], params=params_hyper)
    # The RPC plan's ACT-to-CAS of 16 matches speed-1600. Other profiles must
    # not reuse those cycle numbers.
    rpc_params = params_rpc or RpcDramParams()
    if rpc_params.act_to_cas_ck != 16 or rpc_params.tPPD_act_ck != 8:
        rpc = {"memory": "rpc-dram", "pass": False, "skipped": True,
               "reason": "safe RPC cycles are for the speed-1600 profile"}
    else:
        rpc = evaluate_rpc_trace(plan["rpc"], params=rpc_params)
    return {"plan": plan, "hyperram": hyper, "rpc": rpc,
            "pass": hyper["pass"] and rpc.get("pass", False)}


def dumps(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=2, sort_keys=True)
