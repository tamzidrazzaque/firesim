"""Guard the XB10 deployment path against platform-specific workflow forks."""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest


DEPLOY_DIR = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(DEPLOY_DIR))

import runtools.run_farm_deploy_managers as deploy_managers  # noqa: E402
from runtools.run_farm_deploy_managers import (  # noqa: E402
    CorigineXB10InstanceDeployManager,
    XilinxAlveoInstanceDeployManager,
)


STANDARD_ALVEO_OPERATIONS = (
    "load_xdma",
    "unload_xdma",
    "slot_to_bdf",
    "flash_fpgas",
    "change_pcie_perms",
    "change_all_pcie_perms",
    "infrasetup_instance",
    "create_fpga_database",
    "enumerate_fpgas",
    "terminate_instance",
    "start_sim_slot",
)


def make_parent(*, metasimulation_enabled: bool = False):
    return SimpleNamespace(
        sim_slots=[object()],
        switch_slots=[],
        pipe_slots=[],
        metasimulation_enabled=metasimulation_enabled,
    )


def test_xb10_is_a_direct_standard_alveo_specialization():
    assert CorigineXB10InstanceDeployManager.__bases__ == (
        XilinxAlveoInstanceDeployManager,
    )
    manager = CorigineXB10InstanceDeployManager(make_parent())
    assert manager.PLATFORM_NAME == "corigine_xb10"


@pytest.mark.parametrize("method_name", STANDARD_ALVEO_OPERATIONS)
def test_xb10_inherits_each_operational_method_unchanged(method_name):
    assert (
        getattr(CorigineXB10InstanceDeployManager, method_name)
        is getattr(XilinxAlveoInstanceDeployManager, method_name)
    )


def test_xb10_defines_no_platform_specific_operational_methods():
    locally_defined_callables = {
        name
        for name, value in CorigineXB10InstanceDeployManager.__dict__.items()
        if callable(value)
    }
    assert locally_defined_callables == {"__init__"}


def test_standard_alveo_infrasetup_order_is_used(monkeypatch):
    manager = CorigineXB10InstanceDeployManager(make_parent())
    steps = []
    monkeypatch.setattr(
        manager,
        "copy_sim_slot_infrastructure",
        lambda slot, uri: steps.append(("copy", slot, uri)),
    )
    monkeypatch.setattr(
        manager,
        "extract_driver_tarball",
        lambda slot: steps.append(("extract", slot)),
    )
    for method_name in (
        "unload_xdma",
        "flash_fpgas",
        "load_xdma",
        "change_pcie_perms",
    ):
        monkeypatch.setattr(
            manager,
            method_name,
            lambda name=method_name: steps.append((name,)),
        )

    manager.infrasetup_instance("/uri-cache")

    assert steps == [
        ("copy", 0, "/uri-cache"),
        ("extract", 0),
        ("unload_xdma",),
        ("flash_fpgas",),
        ("load_xdma",),
        ("change_pcie_perms",),
    ]


def test_standard_alveo_helpers_are_the_only_helper_contract():
    source = "\n".join(
        inspect.getsource(getattr(XilinxAlveoInstanceDeployManager, name))
        for name in (
            "load_xdma",
            "unload_xdma",
            "flash_fpgas",
            "change_pcie_perms",
        )
    )
    for helper in (
        "firesim-load-xdma-module",
        "firesim-remove-xdma-module",
        "firesim-chmod-xdma-perm",
        "firesim-fpga-util.py",
        "firesim-change-pcie-perms",
        "program_fpga_fleet.tcl",
    ):
        assert helper in source
    assert "firesim-xb10-card.py" not in source


def test_inherited_sim_infrastructure_rsync_failure_is_fatal(monkeypatch):
    hwcfg = SimpleNamespace(get_local_uri_paths=lambda _uridir: [])
    server = SimpleNamespace(
        get_required_files_local_paths=lambda: [("/local/input", "input")],
        get_resolved_server_hardware_config=lambda: hwcfg,
    )
    manager = CorigineXB10InstanceDeployManager(make_parent())
    manager.parent_node.sim_slots = [server]
    monkeypatch.setattr(manager, "instance_logger", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        manager, "get_remote_sim_dir_for_slot", lambda _slot: "/remote/sim_slot_0/"
    )
    monkeypatch.setattr(deploy_managers, "run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        deploy_managers,
        "rsync_project",
        lambda **_kwargs: SimpleNamespace(failed=True, stderr="mock rsync failure"),
    )

    with pytest.raises(RuntimeError, match="mock rsync failure"):
        manager.copy_sim_slot_infrastructure(0, "/uri-cache")


def test_inherited_contracted_artifact_rsync_uses_checksum(monkeypatch):
    artifact_pair = ("/uri-cache/artifact", "firesim.tar.gz")
    local_verifications = []
    hwcfg = SimpleNamespace(
        artifact_sha256=SimpleNamespace(
            bitstream_tar="a" * 64, driver_tar="b" * 64
        ),
        get_local_uri_paths=lambda _uridir: [artifact_pair],
        verify_local_uri_path=lambda *args: local_verifications.append(args),
    )
    server = SimpleNamespace(
        get_required_files_local_paths=lambda: [("/local/input", "input")],
        get_resolved_server_hardware_config=lambda: hwcfg,
    )
    manager = CorigineXB10InstanceDeployManager(make_parent())
    manager.parent_node.sim_slots = [server]
    monkeypatch.setattr(manager, "instance_logger", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        manager, "get_remote_sim_dir_for_slot", lambda _slot: "/remote/sim_slot_0/"
    )
    monkeypatch.setattr(deploy_managers, "run", lambda *_args, **_kwargs: None)
    rsync_calls = []
    monkeypatch.setattr(
        deploy_managers,
        "rsync_project",
        lambda **kwargs: (
            rsync_calls.append(kwargs)
            or SimpleNamespace(failed=False, stderr="")
        ),
    )

    manager.copy_sim_slot_infrastructure(0, "/uri-cache")

    assert rsync_calls[0]["extra_opts"] == "-L"
    assert rsync_calls[1]["extra_opts"] == "-L --checksum"
    assert local_verifications == [
        ("/uri-cache", "/uri-cache/artifact", "firesim.tar.gz")
    ]
