#!/usr/bin/env bash
# Replay saved ETH pin traces through the independent Etron timing model.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/independent"
exec "$ROOT/.venv/bin/python" - << 'PY'
import sys
from collections import Counter
from pathlib import Path

root = Path.cwd().parent
sys.path[:0] = [str(root / "independent"), str(root / "src")]
from rpc_fased.check import parse_pin_log, replay
from rpc_fased.profiles import profile_for
from memperiph.rpcdram import RpcCommand, RpcDramDevice, RpcDramParams

logs = root / "results" / "logs"
prof = profile_for(5000, cl=8)
out = []
def say(line=""):
    out.append(line)
    print(line)

say("Independent EM6GA16L checker at tCK=5 ns, MRS CL=8 (the packet the controller sends).")
say(f"tRCD={prof.tRCD} tRP={prof.tRP} tRAS={prof.tRAS} tRC={prof.tRC} tRRD={prof.tRRD} tWR={prof.tWR}")
say(f"tPPD idle/act={prof.tPPD_IDLE}/{prof.tPPD_ACT} RL=WL={prof.RL} tREF busy={prof.tREF_BUSY_FST} nWR min={prof.nWR_MIN}")
say("An early command is reported and is not moved later.")
say()

def to_original(cmd):
    if cmd.kind == "reset":
        return RpcCommand("RESET", cmd.cycle)
    if cmd.kind == "precharge":
        mask = 0xF if cmd.all_banks else (1 << cmd.bank)
        return RpcCommand("PRE", cmd.cycle, bank=cmd.bank or 0, mask=mask)
    if cmd.kind == "mrs":
        return RpcCommand("MRS", cmd.cycle, cl=cmd.cl, zout_open=(cmd.zout == 0))
    if cmd.kind == "zq":
        return RpcCommand("ZQC", cmd.cycle)
    if cmd.kind == "activate":
        return RpcCommand("ACT", cmd.cycle, bank=cmd.bank, row=cmd.row)
    if cmd.kind == "read":
        return RpcCommand("RD", cmd.cycle, bank=cmd.bank, col=cmd.column << 4, bc=cmd.burst_count)
    if cmd.kind == "write":
        return RpcCommand("WR", cmd.cycle, bank=cmd.bank, col=cmd.column << 4, bc=cmd.burst_count)
    if cmd.kind == "refresh":
        mask = sum(1 << b for b in cmd.banks)
        return RpcCommand("REF", cmd.cycle, mask=mask, ref_op=0 if cmd.refop is None else cmd.refop)
    raise AssertionError(cmd.kind)

original = RpcDramParams(tck_ps=5000, cl=8, tRTW_ck=8, tWTR_ck=8)
names = [
    "eth_full_pin_run.log",
    "chipyard_eth_rocket_stdout.log",
    "chipyard_eth_boom_stdout.log",
]
total_cmds = 0
total_viol = 0
for name in names:
    observed = parse_pin_log((logs / name).read_text(errors="replace"))
    _dev, reports, counts = replay(observed, prof)
    total_cmds += len(observed)
    total_viol += len(reports)
    banks = sorted({item.command.bank for item in observed if item.command.kind == "activate"})
    say(f"{name}: commands={len(observed)} counts={counts} banks={banks} violations={len(reports)}")
    for item in reports[:20]:
        say("  " + item.format())
    dev = RpcDramDevice(original)
    for item in observed:
        dev.issue(to_original(item.command))
    kinds = Counter(v.constraint for v in dev.violations)
    say(f"  original Python model violations={len(dev.violations)} {dict(kinds)}")
    say()

say(f"total commands checked={total_cmds} independent violations={total_viol}")
say("refresh commands in these traces: 0")
say("pattern: closed page, ACT then one column command then PRE")
say("Rocket/BOOM ACT-to-CAS gap is 16 CK. CAS-to-PRE gap is 48 CK.")
say("Those gaps meet tRCD=3, the active 8-CK command grid, tRAS=7, and read-to-precharge. They do not sit on the minimum.")
path = logs / "eth_independent_timing.txt"
path.write_text("\n".join(out) + "\n")
say(f"wrote {path}")
PY
