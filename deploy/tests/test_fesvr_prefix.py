import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from util.export import FIRESIM_BUILD_ENV_VARS, create_export_string


def test_manager_build_environment_includes_distinct_fesvr_prefix(monkeypatch):
    target_toolchain = "/opt/riscv-target"
    host_fesvr = "/scratch/host-fesvr"
    monkeypatch.setenv("RISCV", target_toolchain)
    monkeypatch.setenv("FIRESIM_FESVR_PREFIX", host_fesvr)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/host/lib")

    export_string = create_export_string(FIRESIM_BUILD_ENV_VARS)

    assignments = set(export_string.removeprefix("export ").split())
    assert f"RISCV={target_toolchain}" in assignments
    assert f"FIRESIM_FESVR_PREFIX={host_fesvr}" in assignments
    assert "PATH=/usr/bin:/bin" in assignments
    assert "LD_LIBRARY_PATH=/opt/host/lib" in assignments


def test_manager_build_environment_omits_unset_fesvr_prefix(monkeypatch):
    monkeypatch.delenv("FIRESIM_FESVR_PREFIX", raising=False)
    monkeypatch.setenv("RISCV", "/opt/riscv-target")

    export_string = create_export_string(FIRESIM_BUILD_ENV_VARS)

    assert "FIRESIM_FESVR_PREFIX=" not in export_string
    assert "RISCV=/opt/riscv-target" in export_string
