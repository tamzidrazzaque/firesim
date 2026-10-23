#!/usr/bin/env python3
"""Perform card-scoped XB10 PCI and permission operations.

This helper intentionally never loads, unloads, or reconfigures the shared
XDMA kernel module.  Each operation resolves one exact PCI function and the
device nodes which sysfs associates with that function.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Sequence, Tuple


PCI_DEVICES = Path("/sys/bus/pci/devices")
DEV_ROOT = Path("/dev")
STATE_DIR = Path("/run/firesim-xb10")
EXPECTED_VENDOR = 0x10EE
EXPECTED_DEVICE = 0x903F
BDF_RE = re.compile(r"^[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}\.[0-7]$")
EXTENDED_BDF_RE = re.compile(r"^0000:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}\.[0-7]$")
DEVNAME_RE = re.compile(r"^xdma[0-9]+_[A-Za-z0-9_]+$")
TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
REQUIRED_SUFFIXES = ("_user", "_h2c_0", "_c2h_0")


class CardError(RuntimeError):
    pass


def _require_root() -> None:
    if os.geteuid() != 0:
        raise CardError("this operation must run as root")


def _extended_bdf(bdf: str) -> str:
    if BDF_RE.fullmatch(bdf) is None:
        raise CardError(f"invalid XB10 BDF: {bdf!r}")
    return f"0000:{bdf.lower()}"


def _read_hex(path: Path) -> int:
    try:
        return int(path.read_text(encoding="ascii").strip(), 16)
    except (OSError, ValueError) as error:
        raise CardError(
            f"cannot read hexadecimal value from {path}: {error}"
        ) from error


def _read_uevent(path: Path) -> Dict[str, str]:
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except OSError as error:
        raise CardError(f"cannot read {path}: {error}") from error
    result: Dict[str, str] = {}
    for line in lines:
        key, separator, value = line.partition("=")
        if separator:
            result[key] = value
    return result


def _card_nodes(endpoint: Path) -> Tuple[List[Path], List[Path]]:
    xdma_dir = endpoint / "xdma"
    if not xdma_dir.is_dir():
        raise CardError(f"{endpoint.name} is not bound to a usable XDMA device")

    nodes: List[Path] = []
    for child in xdma_dir.iterdir():
        uevent = child / "uevent"
        if not uevent.is_file():
            continue
        devname = _read_uevent(uevent).get("DEVNAME", "")
        if DEVNAME_RE.fullmatch(devname) is None:
            raise CardError(f"unexpected XDMA DEVNAME {devname!r} for {endpoint.name}")
        node = DEV_ROOT / devname
        try:
            mode = node.stat().st_mode
        except OSError as error:
            raise CardError(f"missing XDMA node {node}: {error}") from error
        if not stat.S_ISCHR(mode):
            raise CardError(f"XDMA node is not a character device: {node}")
        nodes.append(node)

    nodes = sorted(set(nodes))
    if not nodes:
        raise CardError(f"no XDMA nodes found for {endpoint.name}")

    required: List[Path] = []
    for suffix in REQUIRED_SUFFIXES:
        matches = [node for node in nodes if node.name.endswith(suffix)]
        if len(matches) != 1:
            raise CardError(
                f"expected one {suffix} node for {endpoint.name}, found {len(matches)}"
            )
        required.append(matches[0])
    prefixes = {node.name.split("_", 1)[0] for node in required}
    if len(prefixes) != 1:
        raise CardError(f"required XDMA nodes do not belong to one device: {required}")
    return nodes, required


def _resolve_card(bdf: str) -> Tuple[Path, List[Path], List[Path]]:
    extended = _extended_bdf(bdf)
    endpoint = PCI_DEVICES / extended
    if not endpoint.is_dir():
        raise CardError(f"selected XB10 endpoint is absent: {extended}")
    if _read_hex(endpoint / "vendor") != EXPECTED_VENDOR:
        raise CardError(f"selected endpoint {extended} is not Xilinx vendor 0x10ee")
    if _read_hex(endpoint / "device") != EXPECTED_DEVICE:
        raise CardError(f"selected endpoint {extended} is not XB10 device 0x903f")

    driver = endpoint / "driver"
    if not driver.exists() or driver.resolve().name != "xdma":
        raise CardError(f"selected endpoint {extended} is not bound to xdma")
    nodes, required = _card_nodes(endpoint)
    return endpoint, nodes, required


def _require_tool(name: str) -> str:
    tool = shutil.which(name)
    if tool is None:
        raise CardError(f"{name} is required for safe XB10 deployment")
    return tool


def _check_nodes_idle(nodes: Sequence[Path]) -> None:
    fuser = _require_tool("fuser")
    try:
        result = subprocess.run(
            [fuser, "-s", *map(str, nodes)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as error:
        raise CardError(f"cannot run fuser for selected XB10: {error}") from error
    if result.returncode == 0:
        raise CardError("a process has an XDMA node for the selected XB10 open")
    if result.returncode != 1:
        detail = result.stderr.strip() or f"exit status {result.returncode}"
        raise CardError(f"cannot determine whether selected XB10 is idle: {detail}")


def _run_checked(argv: Sequence[str]) -> None:
    try:
        subprocess.run(list(argv), check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise CardError(f"command failed: {' '.join(argv)}: {error}") from error


def _write_sysfs(path: Path) -> None:
    try:
        path.write_text("1\n", encoding="ascii")
    except OSError as error:
        raise CardError(f"cannot write {path}: {error}") from error


def _bridge_for(endpoint: Path) -> Tuple[str, Path]:
    bridge = endpoint.resolve().parent
    if EXTENDED_BDF_RE.fullmatch(bridge.name) is None:
        raise CardError(f"cannot resolve upstream bridge for {endpoint.name}")
    pci_children = sorted(
        child.name
        for child in bridge.iterdir()
        if child.is_dir() and EXTENDED_BDF_RE.fullmatch(child.name) is not None
    )
    if pci_children != [endpoint.name]:
        raise CardError(
            f"upstream bridge {bridge.name} is not dedicated to {endpoint.name}: "
            f"{pci_children}"
        )
    rescan = PCI_DEVICES / bridge.name / "rescan"
    if not rescan.is_file():
        raise CardError(f"upstream bridge has no rescan control: {bridge.name}")
    return bridge.name, rescan


def _state_file(bdf: str) -> Path:
    return STATE_DIR / f"{_extended_bdf(bdf)}.bridge"


def _validate_token(token: str) -> None:
    if TOKEN_RE.fullmatch(token) is None:
        raise CardError("operation token must be 32 lowercase hexadecimal characters")


def _save_bridge_state(bdf: str, bridge_bdf: str, token: str) -> None:
    _validate_token(token)
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    state = _state_file(bdf)
    try:
        descriptor = os.open(state, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise CardError(
            f"another operation owns selected XB10 state: {state}"
        ) from error
    except OSError as error:
        raise CardError(
            f"cannot reserve reconnect state in {state}: {error}"
        ) from error
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as stream:
            stream.write(f"{token} {bridge_bdf}\n")
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise CardError(
            f"cannot preserve reconnect state in {state}: {error}"
        ) from error


def _load_bridge_state(bdf: str, token: str) -> Tuple[Path, str]:
    _validate_token(token)
    state = _state_file(bdf)
    try:
        fields = state.read_text(encoding="ascii").split()
    except OSError as error:
        raise CardError(f"cannot read reconnect state {state}: {error}") from error
    if len(fields) != 2 or TOKEN_RE.fullmatch(fields[0]) is None:
        raise CardError(f"invalid reconnect state in {state}")
    if fields[0] != token:
        raise CardError(f"selected XB10 state is owned by another operation: {state}")
    bridge_bdf = fields[1]
    if EXTENDED_BDF_RE.fullmatch(bridge_bdf) is None:
        raise CardError(f"invalid saved upstream bridge: {bridge_bdf!r}")
    return state, bridge_bdf


def preflight(bdf: str) -> None:
    _require_root()
    endpoint, nodes, _ = _resolve_card(bdf)
    _bridge_for(endpoint)
    _require_tool("setpci")
    _require_tool("setfacl")
    _check_nodes_idle(nodes)


def disconnect(bdf: str, token: str) -> None:
    _require_root()
    endpoint, nodes, _ = _resolve_card(bdf)
    _check_nodes_idle(nodes)
    bridge_bdf, _ = _bridge_for(endpoint)
    _save_bridge_state(bdf, bridge_bdf, token)

    setpci = _require_tool("setpci")
    _run_checked([setpci, "-s", bridge_bdf, "COMMAND=0000:0100"])
    _run_checked([setpci, "-s", bridge_bdf, "CAP_EXP+8.w=0000:0004"])
    _write_sysfs(endpoint / "remove")

    deadline = time.monotonic() + 10.0
    while endpoint.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    if endpoint.exists():
        raise CardError(f"selected XB10 endpoint did not disappear: {endpoint.name}")


def reconnect(bdf: str, token: str) -> None:
    _require_root()
    extended = _extended_bdf(bdf)
    endpoint = PCI_DEVICES / extended
    state, bridge_bdf = _load_bridge_state(bdf, token)

    if not endpoint.exists():
        rescan = PCI_DEVICES / bridge_bdf / "rescan"
        if not rescan.is_file():
            raise CardError(f"saved upstream bridge is unavailable: {bridge_bdf}")
        _write_sysfs(rescan)

    deadline = time.monotonic() + 15.0
    last_error = "endpoint has not appeared"
    while time.monotonic() < deadline:
        try:
            _resolve_card(bdf)
            break
        except CardError as error:
            last_error = str(error)
            time.sleep(0.1)
    else:
        raise CardError(f"selected XB10 did not reconnect: {last_error}")

    setpci = _require_tool("setpci")
    _run_checked([setpci, "-s", extended, "COMMAND=0x02"])
    try:
        state.unlink()
    except FileNotFoundError:
        pass
    except OSError as error:
        raise CardError(f"cannot remove reconnect state {state}: {error}") from error


def reconnect_if_needed(bdf: str, token: str) -> None:
    """Reconnect only when a prior disconnect created recovery state."""
    _require_root()
    endpoint = PCI_DEVICES / _extended_bdf(bdf)
    if _state_file(bdf).exists() or not endpoint.exists():
        reconnect(bdf, token)


def grant(bdf: str) -> None:
    _require_root()
    _, _, required = _resolve_card(bdf)
    sudo_uid = os.environ.get("SUDO_UID")
    if sudo_uid is None or not sudo_uid.isdecimal():
        raise CardError("grant must be invoked through sudo by the FireSim user")
    setfacl = _require_tool("setfacl")
    _run_checked(
        [setfacl, "--modify", f"user:{int(sudo_uid)}:rw-", "--", *map(str, required)]
    )


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "preflight",
            "disconnect",
            "reconnect",
            "reconnect-if-needed",
            "grant",
        ),
    )
    parser.add_argument(
        "--bdf", required=True, help="exact PCI BDF, for example 1a:00.0"
    )
    parser.add_argument("--token", default="", help="per-operation ownership token")
    args = parser.parse_args(argv)
    try:
        action = args.action.replace("-", "_")
        if action in ("disconnect", "reconnect", "reconnect_if_needed"):
            globals()[action](args.bdf, args.token)
        else:
            globals()[action](args.bdf)
    except CardError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
