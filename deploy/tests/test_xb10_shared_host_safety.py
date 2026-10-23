import importlib.util
import hashlib
import io
import os
import subprocess
import sys
import tarfile
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest


DEPLOY_DIR = Path(__file__).resolve().parents[1]
FIRESIM_DIR = DEPLOY_DIR.parent
CARD_HELPER = (
    FIRESIM_DIR / "platforms" / "xilinx_alveo_u250" / "scripts" / "firesim-xb10-card.py"
)
FLEET_TCL = (
    FIRESIM_DIR
    / "platforms"
    / "xilinx_alveo_u250"
    / "scripts"
    / "program_fpga_fleet.tcl"
)

sys.path.insert(0, str(DEPLOY_DIR))
import runtools.run_farm_deploy_managers as deploy_managers
from runtools.run_farm_deploy_managers import CorigineXB10InstanceDeployManager


def make_manager(slot_count=1):
    parent = SimpleNamespace(
        sim_slots=[object() for _ in range(slot_count)],
        switch_slots=[],
        pipe_slots=[],
        metasimulation_enabled=False,
    )
    return CorigineXB10InstanceDeployManager(parent)


def valid_db():
    return [{"bdf": "1a:00.0", "uid": "Digilent/210308B356F7", "device": "xcvu13p_0"}]


@pytest.mark.parametrize(
    "database",
    [
        [],
        valid_db() * 2,
        [{"bdf": "1a:00.0", "uid": "Digilent/serial"}],
        [{"bdf": "1a:*", "uid": "Digilent/serial", "device": "xcvu13p_0"}],
        [{"bdf": "1a:00.0", "uid": "not-a-uid", "device": "xcvu13p_0"}],
    ],
)
def test_fpga_db_validation_fails_closed(database):
    with pytest.raises(RuntimeError):
        CorigineXB10InstanceDeployManager._validate_fpga_db_entries(database, 1)


def test_fpga_db_validation_rejects_duplicate_bdf_and_uid():
    database = valid_db() + [
        {"bdf": "1A:00.0", "uid": "Digilent/other", "device": "xcvu13p_0"}
    ]
    with pytest.raises(RuntimeError, match="duplicate BDF"):
        CorigineXB10InstanceDeployManager._validate_fpga_db_entries(database, 2)

    database[1]["bdf"] = "1b:00.0"
    database[1]["uid"] = database[0]["uid"]
    with pytest.raises(RuntimeError, match="duplicate JTAG"):
        CorigineXB10InstanceDeployManager._validate_fpga_db_entries(database, 2)


def test_vivado_and_hw_server_are_resolved_before_use(monkeypatch):
    manager = make_manager()
    monkeypatch.setattr(
        deploy_managers,
        "run",
        lambda _command: textwrap.dedent(
            """
            __FIRESIM_VIVADO__=/tools/Vivado/2025.1/bin/vivado
            __FIRESIM_HW_SERVER__=/tools/Vivado/2025.1/bin/hw_server
            __FIRESIM_VIVADO_VERSION__=Vivado v2025.1 (64-bit)
            """
        ),
    )

    environment, vivado, hw_server = manager._preflight_xb10_tools()

    assert "settings64.sh" in environment
    assert vivado.endswith("/vivado")
    assert hw_server.endswith("/hw_server")


def test_wrong_vivado_release_is_rejected(monkeypatch):
    manager = make_manager()
    monkeypatch.setattr(
        deploy_managers,
        "run",
        lambda _command: (
            "__FIRESIM_VIVADO__=/bin/vivado\n"
            "__FIRESIM_HW_SERVER__=/bin/hw_server\n"
            "__FIRESIM_VIVADO_VERSION__=Vivado v2024.1 (64-bit)"
        ),
    )

    with pytest.raises(RuntimeError, match="requires Vivado 2025.1"):
        manager._preflight_xb10_tools()


def test_program_failure_reconnects_all_cards_in_reverse_order(monkeypatch):
    manager = make_manager(2)
    entries = valid_db() + [
        {"bdf": "1b:00.0", "uid": "Digilent/other", "device": "xcvu13p_0"}
    ]
    calls = []

    def fake_action(action, bdf, helper, token, warn=False):
        calls.append((action, bdf, helper, token, warn))
        return SimpleNamespace(return_code=0)

    monkeypatch.setattr(manager, "_run_card_action", fake_action)
    monkeypatch.setattr(
        deploy_managers,
        "run",
        lambda _command: (_ for _ in ()).throw(ValueError("boom")),
    )

    with pytest.raises(ValueError, match="boom"):
        manager._program_with_guaranteed_reconnect(
            entries,
            "/remote/firesim-xb10-card.py",
            "0" * 32,
            "vivado command",
        )

    assert [call[0] for call in calls] == ["reconnect-if-needed"] * 2
    assert [call[1] for call in calls] == ["1b:00.0", "1a:00.0"]
    assert all(call[4] for call in calls)


def test_reconnect_failures_are_not_hidden_and_do_not_stop_cleanup(monkeypatch):
    manager = make_manager(2)
    entries = valid_db() + [
        {"bdf": "1b:00.0", "uid": "Digilent/other", "device": "xcvu13p_0"}
    ]
    attempted = []

    def fake_action(_action, bdf, _helper, _token, warn=False):
        assert warn
        attempted.append(bdf)
        if bdf == "1b:00.0":
            raise OSError("mock reconnect transport failure")
        return SimpleNamespace(return_code=1)

    monkeypatch.setattr(manager, "_run_card_action", fake_action)
    monkeypatch.setattr(deploy_managers, "run", lambda _command: "")

    with pytest.raises(RuntimeError, match=r"1b:00.0, 1a:00.0"):
        manager._program_with_guaranteed_reconnect(
            entries, "/helper", "0" * 32, "vivado"
        )
    assert attempted == ["1b:00.0", "1a:00.0"]


def test_xb10_infrasetup_never_calls_global_xdma_operations(monkeypatch):
    manager = make_manager(2)
    contract = SimpleNamespace(bitstream_tar="a" * 64, driver_tar="b" * 64)
    hwcfg = SimpleNamespace(artifact_sha256=contract)
    manager.parent_node.sim_slots = [
        SimpleNamespace(get_resolved_server_hardware_config=lambda: hwcfg)
        for _ in range(2)
    ]
    steps = []
    monkeypatch.setattr(
        manager,
        "copy_sim_slot_infrastructure",
        lambda slot, uri: steps.append(("copy", slot, uri)),
    )
    monkeypatch.setattr(
        manager,
        "_remove_stale_fased_runtime_profile",
        lambda slot: steps.append(("remove", slot)),
    )
    monkeypatch.setattr(
        manager,
        "extract_driver_tarball",
        lambda slot: steps.append(("extract", slot)),
    )
    monkeypatch.setattr(
        manager,
        "_verify_remote_fased_runtime_profile",
        lambda slot: steps.append(("profile-verify", slot)),
    )
    monkeypatch.setattr(
        manager,
        "_verify_remote_artifact_archive",
        lambda slot, artifact: steps.append(("artifact-verify", slot, artifact)),
    )
    monkeypatch.setattr(manager, "flash_fpgas", lambda: None)
    monkeypatch.setattr(manager, "change_pcie_perms", lambda: None)
    monkeypatch.setattr(
        manager,
        "unload_xdma",
        lambda: pytest.fail("XB10 must not unload the shared XDMA module"),
    )
    monkeypatch.setattr(
        manager,
        "load_xdma",
        lambda: pytest.fail("XB10 must not load or chmod the shared XDMA module"),
    )

    manager.infrasetup_instance("file:///tmp")

    assert steps == [
        ("copy", 0, "file:///tmp"),
        ("artifact-verify", 0, "driver_tar"),
        ("artifact-verify", 0, "bitstream_tar"),
        ("remove", 0),
        ("extract", 0),
        ("profile-verify", 0),
        ("copy", 1, "file:///tmp"),
        ("artifact-verify", 1, "driver_tar"),
        ("artifact-verify", 1, "bitstream_tar"),
        ("remove", 1),
        ("extract", 1),
        ("profile-verify", 1),
    ]


def test_xb10_contracted_profile_is_removed_then_verified(monkeypatch):
    profile = SimpleNamespace(filename="controlled.conf", sha256="a" * 64)
    hwcfg = SimpleNamespace(fased_runtime_profile=profile)
    server = SimpleNamespace(get_resolved_server_hardware_config=lambda: hwcfg)
    manager = make_manager()
    manager.parent_node.sim_slots = [server]
    monkeypatch.setattr(
        manager, "get_remote_sim_dir_for_slot", lambda _slot: "/remote/sim_slot_0/"
    )
    commands = []
    monkeypatch.setattr(deploy_managers, "run", commands.append)

    manager._remove_stale_fased_runtime_profile(0)
    manager._verify_remote_fased_runtime_profile(0)

    assert commands[0] == "rm -f -- /remote/sim_slot_0/controlled.conf"
    assert "! -L" in commands[1]
    assert "-s" in commands[1]
    assert "sha256sum" in commands[1]
    assert "a" * 64 in commands[1]


def test_sim_infrastructure_rsync_failure_is_fatal(monkeypatch):
    hwcfg = SimpleNamespace(get_local_uri_paths=lambda _uridir: [])
    server = SimpleNamespace(
        get_required_files_local_paths=lambda: [("/local/input", "input")],
        get_resolved_server_hardware_config=lambda: hwcfg,
    )
    manager = make_manager()
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


def test_contracted_artifact_rsync_uses_checksum(monkeypatch):
    artifact_pair = ("/uri-cache/artifact", "firesim.tar.gz")
    local_verifications = []
    hwcfg = SimpleNamespace(
        artifact_sha256=SimpleNamespace(bitstream_tar="a" * 64, driver_tar="b" * 64),
        get_local_uri_paths=lambda _uridir: [artifact_pair],
        verify_local_uri_path=lambda *args: local_verifications.append(args),
    )
    server = SimpleNamespace(
        get_required_files_local_paths=lambda: [("/local/input", "input")],
        get_resolved_server_hardware_config=lambda: hwcfg,
    )
    manager = make_manager()
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
            rsync_calls.append(kwargs) or SimpleNamespace(failed=False, stderr="")
        ),
    )

    manager.copy_sim_slot_infrastructure(0, "/uri-cache")

    assert rsync_calls[0]["extra_opts"] == "-L"
    assert rsync_calls[1]["extra_opts"] == "-L --checksum"
    assert local_verifications == [
        ("/uri-cache", "/uri-cache/artifact", "firesim.tar.gz")
    ]


def test_xb10_remote_artifact_checks_exact_archive_hash(monkeypatch):
    hwcfg = SimpleNamespace(
        artifact_sha256=SimpleNamespace(bitstream_tar="a" * 64, driver_tar="b" * 64),
        get_bitstream_tar_filename=lambda: "firesim.tar.gz",
        get_driver_tar_filename=lambda: "driver-bundle.tar.gz",
    )
    server = SimpleNamespace(get_resolved_server_hardware_config=lambda: hwcfg)
    manager = make_manager()
    manager.parent_node.sim_slots = [server]
    monkeypatch.setattr(
        manager, "get_remote_sim_dir_for_slot", lambda _slot: "/remote/sim_slot_0/"
    )
    commands = []
    monkeypatch.setattr(deploy_managers, "run", commands.append)

    manager._verify_remote_artifact_archive(0, "driver_tar")
    manager._verify_remote_artifact_archive(0, "bitstream_tar")

    assert "driver-bundle.tar.gz" in commands[0] and "b" * 64 in commands[0]
    assert "firesim.tar.gz" in commands[1] and "a" * 64 in commands[1]
    for command in commands:
        assert "set -euo pipefail" in command
        assert "-f" in command and "! -L" in command
        assert "-r" in command and "-s" in command
        assert "sha256sum" in command


@pytest.mark.parametrize(
    ("method_name", "args"),
    [("infrasetup_instance", ("/uri-cache",)), ("flash_fpgas", ())],
)
def test_physical_xb10_requires_artifact_contract_before_remote_work(
    monkeypatch, method_name, args
):
    hwcfg = SimpleNamespace(artifact_sha256=None)
    server = SimpleNamespace(get_resolved_server_hardware_config=lambda: hwcfg)
    manager = make_manager()
    manager.parent_node.sim_slots = [server]
    monkeypatch.setattr(
        deploy_managers,
        "run",
        lambda _command: pytest.fail("a missing contract must fail before remote work"),
    )
    monkeypatch.setattr(
        deploy_managers,
        "rsync_project",
        lambda **_kwargs: pytest.fail(
            "a missing contract must fail before artifact transfer"
        ),
    )
    monkeypatch.setattr(
        manager,
        "_read_selected_fpga_db",
        lambda: pytest.fail("a missing contract must fail before reading the FPGA DB"),
    )
    monkeypatch.setattr(
        manager,
        "_preflight_xb10_tools",
        lambda: pytest.fail("a missing contract must fail before Vivado preflight"),
    )

    with pytest.raises(RuntimeError, match="requires an artifact_sha256 contract"):
        getattr(manager, method_name)(*args)


def test_xb10_extracted_bitstream_check_binds_file_to_contracted_archive(
    monkeypatch,
):
    hwcfg = SimpleNamespace(
        artifact_sha256=SimpleNamespace(bitstream_tar="a" * 64, driver_tar="b" * 64),
        get_bitstream_tar_filename=lambda: "firesim.tar.gz",
    )
    server = SimpleNamespace(get_resolved_server_hardware_config=lambda: hwcfg)
    manager = make_manager()
    manager.parent_node.sim_slots = [server]
    monkeypatch.setattr(
        manager, "get_remote_sim_dir_for_slot", lambda _slot: "/remote/sim_slot_0/"
    )
    commands = []
    monkeypatch.setattr(deploy_managers, "run", commands.append)

    manager._verify_remote_extracted_bitstream(0)

    assert len(commands) == 1
    command = commands[0]
    assert "/remote/sim_slot_0/firesim.tar.gz" in command
    assert "/remote/sim_slot_0/corigine_xb10/firesim.bit" in command
    assert "corigine_xb10/firesim.bit" in command
    assert "a" * 64 in command
    assert "-f" in command and "! -L" in command
    assert "-r" in command and "-s" in command
    assert "stat -c %h" in command
    assert "tar -xOzf" in command
    assert '[[ "$actual_bit_sha" == "$archive_bit_sha" ]]' in command


def test_xb10_extracted_bitstream_check_executes_fail_closed(monkeypatch, tmp_path):
    expected_bit = b"contracted bitstream bytes"
    archive = tmp_path / "firesim.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        member = tarfile.TarInfo("corigine_xb10/firesim.bit")
        member.size = len(expected_bit)
        stream.addfile(member, io.BytesIO(expected_bit))
    bit_dir = tmp_path / "corigine_xb10"
    bit_dir.mkdir()
    bit = bit_dir / "firesim.bit"
    bit.write_bytes(expected_bit)
    archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    hwcfg = SimpleNamespace(
        artifact_sha256=SimpleNamespace(
            bitstream_tar=archive_sha, driver_tar="b" * 64
        ),
        get_bitstream_tar_filename=lambda: archive.name,
    )
    server = SimpleNamespace(get_resolved_server_hardware_config=lambda: hwcfg)
    manager = make_manager()
    manager.parent_node.sim_slots = [server]
    monkeypatch.setattr(
        manager, "get_remote_sim_dir_for_slot", lambda _slot: str(tmp_path)
    )
    command = manager._remote_extracted_bitstream_check_command(0)

    assert subprocess.run(["bash", "-c", command]).returncode == 0

    bit.write_bytes(b"changed after extraction")
    assert subprocess.run(["bash", "-c", command]).returncode != 0

    bit.unlink()
    outside = tmp_path / "outside.bit"
    outside.write_bytes(expected_bit)
    bit.symlink_to(outside)
    assert subprocess.run(["bash", "-c", command]).returncode != 0


def test_xb10_unresolved_artifact_hash_fails_before_remote_use(monkeypatch):
    hwcfg = SimpleNamespace(
        artifact_sha256=SimpleNamespace(
            bitstream_tar="__REPLACE_WITH_HBM_FIRESIM_TAR_GZ_SHA256__",
            driver_tar="b" * 64,
        )
    )
    server = SimpleNamespace(get_resolved_server_hardware_config=lambda: hwcfg)
    manager = make_manager()
    manager.parent_node.sim_slots = [server]
    monkeypatch.setattr(
        deploy_managers,
        "run",
        lambda _command: pytest.fail("an unresolved hash must fail before remote use"),
    )

    with pytest.raises(RuntimeError, match="Unresolved bitstream_tar"):
        manager._verify_remote_artifact_archive(0, "bitstream_tar")


def test_xb10_artifact_verification_failure_prevents_extract_and_flash(monkeypatch):
    manager = make_manager()
    contract = SimpleNamespace(bitstream_tar="a" * 64, driver_tar="b" * 64)
    hwcfg = SimpleNamespace(artifact_sha256=contract)
    manager.parent_node.sim_slots = [
        SimpleNamespace(get_resolved_server_hardware_config=lambda: hwcfg)
    ]
    steps = []
    monkeypatch.setattr(
        manager,
        "copy_sim_slot_infrastructure",
        lambda slot, uri: steps.append(("copy", slot, uri)),
    )

    def fail_verification(slot, artifact):
        steps.append(("artifact-verify", slot, artifact))
        raise RuntimeError("mock archive hash mismatch")

    monkeypatch.setattr(manager, "_verify_remote_artifact_archive", fail_verification)
    monkeypatch.setattr(
        manager,
        "extract_driver_tarball",
        lambda _slot: pytest.fail("a failed archive check must prevent extraction"),
    )
    monkeypatch.setattr(
        manager,
        "flash_fpgas",
        lambda: pytest.fail("a failed archive check must prevent programming"),
    )

    with pytest.raises(RuntimeError, match="mock archive hash mismatch"):
        manager.infrasetup_instance("/uri-cache")

    assert steps == [
        ("copy", 0, "/uri-cache"),
        ("artifact-verify", 0, "driver_tar"),
    ]


def test_xb10_rechecks_bitstream_hash_before_unpacking_or_programming(monkeypatch):
    hwcfg = SimpleNamespace(
        artifact_sha256=SimpleNamespace(bitstream_tar="a" * 64, driver_tar="b" * 64),
        get_bitstream_tar_filename=lambda: "firesim.tar.gz",
    )
    server = SimpleNamespace(get_resolved_server_hardware_config=lambda: hwcfg)
    manager = make_manager()
    manager.parent_node.sim_slots = [server]
    monkeypatch.setattr(manager, "_read_selected_fpga_db", lambda: ("db", valid_db()))
    monkeypatch.setattr(
        manager,
        "_preflight_xb10_tools",
        lambda: ("source /tools/settings64.sh", "/tools/vivado", "/tools/hw_server"),
    )
    monkeypatch.setattr(
        manager, "get_remote_sim_dir_for_slot", lambda _slot: "/remote/sim_slot_0/"
    )
    monkeypatch.setattr(
        manager,
        "_verify_remote_artifact_archive",
        lambda _slot, _artifact: (_ for _ in ()).throw(
            RuntimeError("mock pre-program hash mismatch")
        ),
    )
    monkeypatch.setattr(
        deploy_managers,
        "run",
        lambda _command: pytest.fail("verification must precede unpack commands"),
    )
    monkeypatch.setattr(
        manager,
        "_program_with_guaranteed_reconnect",
        lambda *_args, **_kwargs: pytest.fail("programming must not start"),
    )

    with pytest.raises(RuntimeError, match="mock pre-program hash mismatch"):
        manager.flash_fpgas()


def test_xb10_helper_script_rsync_failure_prevents_programming(monkeypatch):
    hwcfg = SimpleNamespace(
        artifact_sha256=SimpleNamespace(bitstream_tar="a" * 64, driver_tar="b" * 64),
        get_bitstream_tar_filename=lambda: "firesim.tar.gz",
    )
    server = SimpleNamespace(get_resolved_server_hardware_config=lambda: hwcfg)
    manager = make_manager()
    manager.parent_node.sim_slots = [server]
    monkeypatch.setattr(manager, "_read_selected_fpga_db", lambda: ("db", valid_db()))
    monkeypatch.setattr(
        manager,
        "_preflight_xb10_tools",
        lambda: ("source /tools/settings64.sh", "/tools/vivado", "/tools/hw_server"),
    )
    monkeypatch.setattr(
        manager, "get_remote_sim_dir_for_slot", lambda _slot: "/remote/sim_slot_0/"
    )
    remote_commands = []
    monkeypatch.setattr(deploy_managers, "run", remote_commands.append)
    monkeypatch.setattr(
        deploy_managers,
        "rsync_project",
        lambda **_kwargs: SimpleNamespace(
            failed=True, stderr="mock helper rsync failure"
        ),
    )
    monkeypatch.setattr(
        manager,
        "_program_with_guaranteed_reconnect",
        lambda *_args, **_kwargs: pytest.fail("programming must not start"),
    )

    with pytest.raises(RuntimeError, match="mock helper rsync failure"):
        manager.flash_fpgas()

    assert not any("flash_map.txt" in command for command in remote_commands)


def test_xb10_final_vivado_command_rechecks_extracted_bitstream(monkeypatch):
    hwcfg = SimpleNamespace(
        artifact_sha256=SimpleNamespace(bitstream_tar="a" * 64, driver_tar="b" * 64),
        get_bitstream_tar_filename=lambda: "firesim.tar.gz",
    )
    server = SimpleNamespace(get_resolved_server_hardware_config=lambda: hwcfg)
    manager = make_manager()
    manager.parent_node.sim_slots = [server]
    monkeypatch.setattr(manager, "_read_selected_fpga_db", lambda: ("db", valid_db()))
    monkeypatch.setattr(
        manager,
        "_preflight_xb10_tools",
        lambda: ("source /tools/settings64.sh", "/tools/vivado", "/tools/hw_server"),
    )
    monkeypatch.setattr(
        manager, "get_remote_sim_dir_for_slot", lambda _slot: "/remote/sim_slot_0/"
    )
    monkeypatch.setattr(manager, "_verify_remote_artifact_archive", lambda *_args: None)
    extracted_checks = []
    monkeypatch.setattr(
        manager,
        "_verify_remote_extracted_bitstream",
        lambda slot: extracted_checks.append(slot),
    )
    monkeypatch.setattr(deploy_managers, "run", lambda _command: None)
    monkeypatch.setattr(
        deploy_managers,
        "rsync_project",
        lambda **_kwargs: SimpleNamespace(failed=False, stderr=""),
    )
    program_calls = []
    monkeypatch.setattr(
        manager,
        "_program_with_guaranteed_reconnect",
        lambda *args: program_calls.append(args),
    )

    manager.flash_fpgas()

    assert extracted_checks == [0]
    assert len(program_calls) == 1
    program_command = program_calls[0][3]
    assert "tar -xOzf" in program_command
    assert "a" * 64 in program_command
    assert program_command.index("sha256sum") < program_command.index(
        "source /tools/settings64.sh"
    )
    assert program_command.index("source /tools/settings64.sh") < program_command.index(
        "/tools/vivado"
    )


def test_xb10_enumeration_fails_closed():
    with pytest.raises(RuntimeError, match="host-global XDMA state"):
        make_manager().enumerate_fpgas("file:///tmp")


def test_xb10_database_creation_fails_closed_before_remote_action(monkeypatch):
    monkeypatch.setattr(
        deploy_managers,
        "run",
        lambda _command: pytest.fail(
            "disabled database creation must not run remotely"
        ),
    )

    with pytest.raises(RuntimeError, match="database creation is disabled"):
        make_manager().create_fpga_database("file:///tmp")


@pytest.fixture
def card_module():
    spec = importlib.util.spec_from_file_location("firesim_xb10_card", CARD_HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_card_grant_uses_acl_on_only_selected_required_nodes(card_module, monkeypatch):
    required = [
        Path("/dev/xdma7_user"),
        Path("/dev/xdma7_h2c_0"),
        Path("/dev/xdma7_c2h_0"),
    ]
    commands = []
    monkeypatch.setattr(card_module.os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_UID", "1234")
    monkeypatch.setattr(
        card_module, "_resolve_card", lambda _bdf: (Path("/sys/card"), [], required)
    )
    monkeypatch.setattr(card_module.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(card_module, "_run_checked", commands.append)

    card_module.grant("1a:00.0")

    assert commands == [
        [
            "/usr/bin/setfacl",
            "--modify",
            "user:1234:rw-",
            "--",
            *map(str, required),
        ]
    ]
    assert not any("xdma*" in argument for argument in commands[0])


def test_card_preflight_rejects_open_selected_nodes(card_module, monkeypatch):
    monkeypatch.setattr(card_module.shutil, "which", lambda _name: "/usr/bin/fuser")
    monkeypatch.setattr(
        card_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stderr=""),
    )

    with pytest.raises(card_module.CardError, match="process has an XDMA node"):
        card_module._check_nodes_idle([Path("/dev/xdma7_user")])


@pytest.mark.parametrize("missing_tool", ["setpci", "setfacl"])
def test_card_preflight_requires_later_tools_before_idle_check(
    card_module, monkeypatch, missing_tool
):
    endpoint = Path("/sys/card")
    nodes = [Path("/dev/xdma7_user")]
    idle_checks = []
    monkeypatch.setattr(card_module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        card_module, "_resolve_card", lambda _bdf: (endpoint, nodes, nodes)
    )
    monkeypatch.setattr(
        card_module,
        "_bridge_for",
        lambda _endpoint: ("0000:19:02.0", Path("/sys/bridge/rescan")),
    )
    monkeypatch.setattr(
        card_module.shutil,
        "which",
        lambda name: None if name == missing_tool else f"/usr/bin/{name}",
    )
    monkeypatch.setattr(card_module, "_check_nodes_idle", idle_checks.append)

    with pytest.raises(card_module.CardError, match=missing_tool):
        card_module.preflight("1a:00.0")

    assert idle_checks == []


def test_reconnect_if_needed_is_noop_without_recovery_state(
    card_module, monkeypatch, tmp_path
):
    endpoint = tmp_path / "pci" / "0000:1a:00.0"
    endpoint.mkdir(parents=True)
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(card_module, "PCI_DEVICES", endpoint.parent)
    monkeypatch.setattr(card_module, "STATE_DIR", state)
    monkeypatch.setattr(card_module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        card_module,
        "reconnect",
        lambda _bdf: pytest.fail("a clean preflight failure must not mutate PCI"),
    )

    card_module.reconnect_if_needed("1a:00.0", "0" * 32)


def test_card_recovery_state_cannot_be_stolen_by_concurrent_operation(
    card_module, monkeypatch, tmp_path
):
    monkeypatch.setattr(card_module, "STATE_DIR", tmp_path / "state")
    card_module._save_bridge_state("1a:00.0", "0000:19:02.0", "0" * 32)

    with pytest.raises(card_module.CardError, match="another operation owns"):
        card_module._save_bridge_state("1a:00.0", "0000:19:02.0", "1" * 32)
    with pytest.raises(card_module.CardError, match="owned by another operation"):
        card_module._load_bridge_state("1a:00.0", "1" * 32)


def run_mocked_tcl(tmp_path, map_identity, extra_args=(), environment=None):
    bitstream = tmp_path / "firesim.bit"
    bitstream.write_bytes(b"mock")
    map_file = tmp_path / "map.txt"
    map_file.write_text(f"{map_identity} {bitstream}\n", encoding="utf-8")
    wrapper = tmp_path / "wrapper.tcl"
    wrapper.write_text(
        textwrap.dedent(
            f"""
            proc set_param {{args}} {{}}
            proc open_hw_manager {{}} {{}}
            proc connect_hw_server {{args}} {{}}
            proc close_hw_target {{}} {{}}
            proc get_hw_targets {{}} {{ return [list target0] }}
            proc get_property {{property target}} {{ return "Digilent/serial" }}
            proc open_hw_target {{target}} {{}}
            proc get_hw_devices {{}} {{ return [list xcvu13p_0] }}
            proc disconnect_hw_server {{}} {{}}
            proc close_hw_manager {{}} {{}}
            proc current_hw_device {{device}} {{}}
            proc set_property {{args}} {{}}
            proc program_hw_devices {{device}} {{}}
            proc refresh_hw_device {{device}} {{}}
            set argc {2 + len(extra_args)}
            set argv [list -map_file {{{map_file}}} {' '.join(map(str, extra_args))}]
            source {{{FLEET_TCL}}}
            """
        ),
        encoding="utf-8",
    )
    return subprocess.run(
        ["tclsh", str(wrapper)],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ if environment is None else environment,
    )


def test_tcl_preflight_resolves_exact_uid_and_device_without_disconnect(tmp_path):
    result = run_mocked_tcl(
        tmp_path,
        "Digilent/serial|xcvu13p_0|1a:00.0",
        ("-preflight_only", "1"),
    )

    assert result.returncode == 0, result.stderr
    assert "Preflight passed" in result.stdout


def test_tcl_uid_failure_happens_before_disconnect(tmp_path):
    helper = tmp_path / "must-not-run"
    helper.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    helper.chmod(0o755)
    result = run_mocked_tcl(
        tmp_path,
        "Digilent/wrong|xcvu13p_0|1a:00.0",
        ("-disconnect_helper", str(helper), "-operation_token", "0" * 32),
    )

    assert result.returncode != 0
    assert "expected exactly one hw_target" in result.stdout


def test_tcl_disconnects_exact_bdf_only_after_successful_preflight(tmp_path):
    helper_log = tmp_path / "helper.log"
    helper = tmp_path / "card-helper"
    helper.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$HELPER_LOG"\n',
        encoding="utf-8",
    )
    helper.chmod(0o755)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    sudo = fake_bin / "sudo"
    sudo.write_text(
        '#!/bin/sh\n[ "${1:-}" != -- ] || shift\nexec "$@"\n', encoding="utf-8"
    )
    sudo.chmod(0o755)
    environment = dict(os.environ)
    environment["PATH"] = f"{fake_bin}:/usr/bin:/bin"
    environment["HELPER_LOG"] = str(helper_log)

    result = run_mocked_tcl(
        tmp_path,
        "Digilent/serial|xcvu13p_0|1a:00.0",
        ("-disconnect_helper", str(helper), "-operation_token", "0" * 32),
        environment,
    )

    assert result.returncode == 0, result.stderr
    assert helper_log.read_text(encoding="utf-8").strip() == (
        f"disconnect --bdf 1a:00.0 --token {'0' * 32}"
    )
