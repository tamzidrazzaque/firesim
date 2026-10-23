import os

from typing import AbstractSet, FrozenSet


# Environment needed by manager-spawned FireSim build commands. Keep the
# target cross-toolchain prefix (RISCV) independent from an optional host-only
# FESVR installation.
FIRESIM_BUILD_ENV_VARS: FrozenSet[str] = frozenset(
    {"RISCV", "FIRESIM_FESVR_PREFIX", "PATH", "LD_LIBRARY_PATH"}
)


def create_export_string(vars: AbstractSet[str]) -> str:
    """For v in vars, if v exists, then add it to an export string"""
    export_shell_env_vars = set()
    for v in vars:
        if v in os.environ:
            export_shell_env_vars.add(f"{v}={os.environ[v]}")
    return (
        ("export " + " ".join(export_shell_env_vars))
        if export_shell_env_vars
        else "true"
    )
