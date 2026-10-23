import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtools.runtime_config as runtime_config
from runtools.runtime_config import (
    ArtifactSHA256Contract,
    CUSTOM_RUNTIMECONFS_BASE,
    FASEDRuntimeProfile,
    RuntimeHWConfig,
    URIContainer,
)


DEPLOY_DIR = Path(__file__).resolve().parents[1]
CANONICAL_PROFILES = (
    (
        "hbm2-FRFCFS-2400-OP-REFab-5bridge.conf",
        "372af4e4a05a168bcdcc37dd853f6dbf3849b6c3585fc595b31522290f852cf8",
        34,
    ),
    (
        "hbm2-FRFCFS-2000-OP-REFab-5bridge.conf",
        "2d45764907b723a66dc30a4547f9ed10d122a9da8132e5380febac76f80fd5ab",
        34,
    ),
    (
        "ddr3-FRFCFS-8G-4R-2133-OP-5bridge.conf",
        "dc133659c8f8e4a8cfd14e6779a373bbcb005cc7143507320d1edf5e1014fc6a",
        28,
    ),
)


def make_hwconfig(
    custom_runtime_config,
    fased_runtime_profile=None,
    artifact_sha256=None,
    bitstream_tar=None,
    driver_tar=None,
):
    hwconfig = {"custom_runtime_config": custom_runtime_config}
    if fased_runtime_profile is not None:
        hwconfig["fased_runtime_profile"] = fased_runtime_profile
    if artifact_sha256 is not None:
        hwconfig["artifact_sha256"] = artifact_sha256
    if bitstream_tar is not None:
        hwconfig["bitstream_tar"] = bitstream_tar
    if driver_tar is not None:
        hwconfig["driver_tar"] = driver_tar
    return RuntimeHWConfig("test-hwdb-entry", hwconfig, "test-config-hwdb.yaml")


def make_contract(profile_bytes, settings_per_model=28):
    return {
        "sha256": hashlib.sha256(profile_bytes).hexdigest(),
        "model_ids": [0, 1, 2, 3, 4],
        "settings_per_model": settings_per_model,
    }


def make_profile_bytes(settings_per_model=28, model_ids=range(5), overrides=None):
    overrides = overrides or {}
    lines = []
    for model_id in model_ids:
        for setting_id in range(settings_per_model):
            value = overrides.get((model_id, setting_id), setting_id)
            lines.append(f"+mm_setting{setting_id}_{model_id}={value}\n")
    return "".join(lines).encode("ascii")


def load_temp_profile(
    monkeypatch,
    tmp_path,
    profile_bytes,
    settings_per_model=28,
    filename="profile.conf",
):
    monkeypatch.setattr(runtime_config, "CUSTOM_RUNTIMECONFS_BASE", str(tmp_path))
    (tmp_path / filename).write_bytes(profile_bytes)
    return make_hwconfig(
        filename, make_contract(profile_bytes, settings_per_model=settings_per_model)
    )


def make_contracted_config(filename, profile_bytes, settings_per_model=28):
    config = object.__new__(RuntimeHWConfig)
    config.name = "test-hwdb-entry"
    config.customruntimeconfig = filename
    config.fased_runtime_profile = FASEDRuntimeProfile(
        filename=filename,
        sha256=hashlib.sha256(profile_bytes).hexdigest(),
        model_ids=(0, 1, 2, 3, 4),
        settings_per_model=settings_per_model,
    )
    return config


def boot_command(
    config,
    monkeypatch,
    extra_plusargs="",
    extra_args="",
    all_bootbinaries=None,
    tracerv_select="0",
):
    monkeypatch.setattr(runtime_config, "is_on_aws", lambda: False)
    config.get_local_driver_binaryname = lambda: "fake-driver"
    return config.get_boot_simulation_command(
        slotid=0,
        all_macs=[None],
        all_rootfses=[None],
        all_linklatencies=[0],
        all_netbws=[0],
        profile_interval=-1,
        all_bootbinaries=all_bootbinaries or ["boot.bin"],
        all_shmemportnames=[None],
        tracerv_config=SimpleNamespace(
            enable=False,
            select=tracerv_select,
            start="0",
            end="-1",
            output_format="0",
        ),
        autocounter_config=SimpleNamespace(readrate=0),
        hostdebug_config=SimpleNamespace(
            zero_out_dram=False, disable_synth_asserts=False
        ),
        synthprint_config=SimpleNamespace(cycle_prefix=True, start="0", end="-1"),
        partition_config=SimpleNamespace(is_partitioned=lambda: False),
        cutbridge_idxs=[],
        extra_plusargs=extra_plusargs,
        extra_args=extra_args,
    )


def install_fake_screen(tmp_path, monkeypatch, exit_status=0):
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_screen = fake_bin / "screen"
    fake_screen.write_text(
        "#!/bin/bash\n"
        ': "${SCREEN_MARKER:?}"\n'
        'printf \'%s\\n\' "$*" > "$SCREEN_MARKER"\n'
        f"exit {exit_status}\n",
        encoding="utf-8",
    )
    fake_screen.chmod(0o755)
    marker = tmp_path / "screen-invoked"
    monkeypatch.setenv("SCREEN_MARKER", str(marker))
    return fake_screen, marker


def run_with_fake_screen(command, fake_screen, tmp_path):
    shell_command = (
        f"screen() {{ {shlex.quote(str(fake_screen))} \"$@\"; }}\n" + command
    )
    return subprocess.run(
        ["/bin/bash", "-c", shell_command],
        cwd=tmp_path,
        env=os.environ.copy(),
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    ("configured_name", "expected"),
    [
        (None, None),
        (
            "five-bridge.conf",
            os.path.join(CUSTOM_RUNTIMECONFS_BASE, "five-bridge.conf"),
        ),
        (
            "/five-bridge.conf",
            os.path.join(CUSTOM_RUNTIMECONFS_BASE, "five-bridge.conf"),
        ),
    ],
)
def test_local_runtime_conf_path(configured_name, expected):
    config = object.__new__(RuntimeHWConfig)
    config.customruntimeconfig = configured_name

    assert config.get_local_runtime_conf_path() == expected


@pytest.mark.parametrize(
    ("configured_name", "expected_sha256", "settings_per_model"),
    CANONICAL_PROFILES,
)
def test_canonical_runtime_profile_contract(
    configured_name, expected_sha256, settings_per_model
):
    contract = {
        "sha256": expected_sha256,
        "model_ids": [0, 1, 2, 3, 4],
        "settings_per_model": settings_per_model,
    }
    config = make_hwconfig(configured_name, contract)

    resolved_path = (DEPLOY_DIR / config.get_local_runtime_conf_path()).resolve()
    expected_directory = (DEPLOY_DIR / CUSTOM_RUNTIMECONFS_BASE).resolve()

    assert resolved_path.parent == expected_directory
    assert resolved_path.is_file()
    assert hashlib.sha256(resolved_path.read_bytes()).hexdigest() == expected_sha256
    assert len(resolved_path.read_text(encoding="ascii").splitlines()) == (
        settings_per_model * 5
    )
    assert config.fased_runtime_profile == FASEDRuntimeProfile(
        filename=configured_name,
        sha256=expected_sha256,
        model_ids=(0, 1, 2, 3, 4),
        settings_per_model=settings_per_model,
    )


def test_runtime_config_without_contract_retains_generic_behavior(monkeypatch):
    config = make_hwconfig("missing-legacy-profile.conf")

    command = boot_command(
        config,
        monkeypatch,
        extra_plusargs="+mm_legacy_0=1",
        extra_args="+mm_trailing_0=2",
    )

    assert config.fased_runtime_profile is None
    assert "$(sed ':a;N;$!ba;s/\\n/ /g' missing-legacy-profile.conf)" in command
    assert "+mm_legacy_0=1" in command
    assert "+mm_trailing_0=2" in command
    assert "set -euo pipefail" not in command


@pytest.mark.parametrize(
    ("raw_contract", "message"),
    [
        ([], "must be a mapping"),
        ({"sha256": "0" * 64}, "fields must be exactly"),
        (
            {
                "sha256": "A" * 64,
                "model_ids": [0, 1, 2, 3, 4],
                "settings_per_model": 28,
            },
            "invalid FASED profile SHA-256",
        ),
        (
            {
                "sha256": "0" * 64,
                "model_ids": [0, 1, 2, 3],
                "settings_per_model": 28,
            },
            "must be exactly",
        ),
        (
            {
                "sha256": "0" * 64,
                "model_ids": [0, 1, 2, 3, 4],
                "settings_per_model": 29,
            },
            "must be 28 or 34",
        ),
    ],
)
def test_malformed_profile_contract_is_rejected(raw_contract, message):
    with pytest.raises(ValueError, match=message):
        make_hwconfig("profile.conf", raw_contract)


def test_explicit_null_profile_contract_is_rejected():
    hwconfig = {
        "custom_runtime_config": "profile.conf",
        "fased_runtime_profile": None,
    }

    with pytest.raises(ValueError, match="must be a mapping"):
        RuntimeHWConfig("test-hwdb-entry", hwconfig, "test-config-hwdb.yaml")


@pytest.mark.parametrize(
    "filename",
    [
        None,
        "",
        ".",
        "..",
        "/profile.conf",
        "../profile.conf",
        "dir/profile.conf",
        "dir\\profile.conf",
    ],
)
def test_contracted_profile_requires_safe_bare_filename(filename):
    with pytest.raises(ValueError, match="safe bare filename"):
        make_hwconfig(filename, make_contract(make_profile_bytes()))


def test_contracted_profile_rejects_missing_file(monkeypatch, tmp_path):
    profile_bytes = make_profile_bytes()
    monkeypatch.setattr(runtime_config, "CUSTOM_RUNTIMECONFS_BASE", str(tmp_path))

    with pytest.raises(ValueError, match="missing, unreadable, or not a regular file"):
        make_hwconfig("missing.conf", make_contract(profile_bytes))


def test_contracted_profile_rejects_unreadable_file(monkeypatch, tmp_path):
    profile_bytes = make_profile_bytes()
    profile_path = tmp_path / "profile.conf"
    profile_path.write_bytes(profile_bytes)
    real_access = os.access

    def deny_profile_read(path, mode):
        if Path(path) == profile_path and mode == os.R_OK:
            return False
        return real_access(path, mode)

    monkeypatch.setattr(runtime_config, "CUSTOM_RUNTIMECONFS_BASE", str(tmp_path))
    monkeypatch.setattr(runtime_config.os, "access", deny_profile_read)

    with pytest.raises(ValueError, match="missing, unreadable, or not a regular file"):
        make_hwconfig(profile_path.name, make_contract(profile_bytes))


def test_contracted_profile_rejects_empty_file(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="profile is empty"):
        load_temp_profile(monkeypatch, tmp_path, b"")


def test_contracted_profile_rejects_symlink(monkeypatch, tmp_path):
    profile_bytes = make_profile_bytes()
    target = tmp_path / "target.conf"
    target.write_bytes(profile_bytes)
    link = tmp_path / "profile.conf"
    link.symlink_to(target)
    monkeypatch.setattr(runtime_config, "CUSTOM_RUNTIMECONFS_BASE", str(tmp_path))

    with pytest.raises(ValueError, match="must not be a symlink"):
        make_hwconfig(link.name, make_contract(profile_bytes))


def test_contracted_profile_rejects_wrong_hash(monkeypatch, tmp_path):
    profile_bytes = make_profile_bytes()
    contract = make_contract(profile_bytes)
    contract["sha256"] = "0" * 64
    monkeypatch.setattr(runtime_config, "CUSTOM_RUNTIMECONFS_BASE", str(tmp_path))
    (tmp_path / "profile.conf").write_bytes(profile_bytes)

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        make_hwconfig("profile.conf", contract)


@pytest.mark.parametrize(
    ("profile_bytes", "message"),
    [
        (make_profile_bytes() + b"not-a-plusarg\n", "line 141"),
        (
            make_profile_bytes() + b"+mm_setting0_0=999\n",
            "duplicates model 0 setting setting0",
        ),
        (make_profile_bytes(model_ids=range(4)), "model 4 has 0 settings"),
        (
            make_profile_bytes(overrides={(4, 0): 999}),
            "model 4 settings do not exactly match model 0",
        ),
        (make_profile_bytes(settings_per_model=27), "model 0 has 27 settings"),
        (
            make_profile_bytes(overrides={(0, 0): 0x100000000}),
            "line 1 value exceeds UINT32_MAX",
        ),
        (
            make_profile_bytes().replace(b"\n", b"\r\n"),
            "must use LF line endings",
        ),
        (
            make_profile_bytes().replace(b"_0=", b"_00=", 1),
            "line 1 has noncanonical model id 00",
        ),
        (
            make_profile_bytes().replace(b"\n", b"\x0b", 1),
            "line 1",
        ),
    ],
    ids=[
        "malformed-line",
        "duplicate-key",
        "missing-model",
        "unequal-model",
        "wrong-count",
        "value-overflow",
        "crlf",
        "zero-padded-model-id",
        "vertical-tab-separator",
    ],
)
def test_contracted_profile_rejects_invalid_content(
    monkeypatch, tmp_path, profile_bytes, message
):
    with pytest.raises(ValueError, match=message):
        load_temp_profile(monkeypatch, tmp_path, profile_bytes)


def test_contracted_profile_accepts_uint32_max(monkeypatch, tmp_path):
    overrides = {(model_id, 0): 0xFFFFFFFF for model_id in range(5)}
    profile_bytes = make_profile_bytes(overrides=overrides)

    config = load_temp_profile(monkeypatch, tmp_path, profile_bytes)

    assert config.fased_runtime_profile is not None


def test_contracted_profile_rejects_non_ascii(monkeypatch, tmp_path):
    profile_bytes = make_profile_bytes() + b"\xff\n"

    with pytest.raises(ValueError, match="must be ASCII"):
        load_temp_profile(monkeypatch, tmp_path, profile_bytes)


@pytest.mark.parametrize(
    ("extra_plusargs", "extra_args"),
    [("+mm_injected_0=1", ""), ("", "+mm_injected_0=1")],
)
def test_contracted_profile_rejects_out_of_band_mm_arguments(
    monkeypatch, extra_plusargs, extra_args
):
    config = make_contracted_config("profile.conf", make_profile_bytes())

    with pytest.raises(ValueError, match=r"forbids out-of-band \+mm_"):
        boot_command(
            config,
            monkeypatch,
            extra_plusargs=extra_plusargs,
            extra_args=extra_args,
        )


@pytest.mark.parametrize("channel", ["extra_plusargs", "extra_args"])
@pytest.mark.parametrize(
    "payload",
    [
        "$(printf +mm%s _injected_0=7)",
        ";+mm_injected_0=7",
        "'+mm_injected_0=7'",
        '"+mm_injected_0=7"',
        "`printf +mm_injected_0=7`",
        "$FASED_INJECT",
    ],
)
def test_contracted_profile_rejects_shell_expansion_and_metacharacters(
    monkeypatch, channel, payload
):
    config = make_contracted_config("profile.conf", make_profile_bytes())
    arguments = {"extra_plusargs": "", "extra_args": ""}
    arguments[channel] = payload

    with pytest.raises(ValueError, match="unsafe shell character"):
        boot_command(config, monkeypatch, **arguments)


def test_contracted_profile_accepts_only_inert_extra_tokens(monkeypatch):
    config = make_contracted_config("profile.conf", make_profile_bytes())

    command = boot_command(
        config,
        monkeypatch,
        extra_plusargs="+safe-plusarg=1",
        extra_args="/safe/path +safe-arg=2",
    )

    assert "+safe-plusarg=1" in command
    assert "/safe/path +safe-arg=2" in command


@pytest.mark.parametrize(
    "arguments",
    [
        {"all_bootbinaries": ["boot.bin +mm_injected_0=7"]},
        {"tracerv_select": "0 +mm_injected_0=7"},
        {"all_bootbinaries": ["boot.bin;touch-marker"]},
        {"tracerv_select": "$(printf +mm_injected_0=7)"},
    ],
)
def test_contracted_profile_rejects_injection_from_generated_arguments(
    monkeypatch, arguments
):
    config = make_contracted_config("profile.conf", make_profile_bytes())

    with pytest.raises(ValueError, match="unsafe generated token"):
        boot_command(config, monkeypatch, **arguments)


@pytest.mark.parametrize("source_state", ["missing", "wrong-hash", "symlink", "empty"])
def test_profile_preflight_failure_never_invokes_screen(
    monkeypatch, tmp_path, source_state
):
    profile_bytes = make_profile_bytes()
    profile_path = tmp_path / "profile.conf"
    if source_state == "wrong-hash":
        profile_path.write_bytes(profile_bytes + b"changed\n")
    elif source_state == "symlink":
        target = tmp_path / "target.conf"
        target.write_bytes(profile_bytes)
        profile_path.symlink_to(target)
    elif source_state == "empty":
        profile_path.write_bytes(b"")

    config = make_contracted_config(profile_path.name, profile_bytes)
    fake_screen, marker = install_fake_screen(tmp_path, monkeypatch)
    command = boot_command(config, monkeypatch)
    result = run_with_fake_screen(command, fake_screen, tmp_path)

    assert result.returncode != 0
    assert not marker.exists()
    assert not (tmp_path / config.fased_runtime_profile.snapshot_filename).exists()
    assert not (tmp_path / "fased-runtime-profile.applied.json").exists()


def test_profile_preflight_rejects_stale_snapshot_directory(monkeypatch, tmp_path):
    profile_bytes = make_profile_bytes()
    profile_path = tmp_path / "profile.conf"
    profile_path.write_bytes(profile_bytes)
    config = make_contracted_config(profile_path.name, profile_bytes)
    snapshot = tmp_path / config.fased_runtime_profile.snapshot_filename
    snapshot.mkdir()
    receipt = tmp_path / "fased-runtime-profile.applied.json"
    receipt.write_text("stale\n", encoding="utf-8")
    fake_screen, marker = install_fake_screen(tmp_path, monkeypatch)

    result = run_with_fake_screen(
        boot_command(config, monkeypatch), fake_screen, tmp_path
    )

    assert result.returncode != 0
    assert not marker.exists()
    assert snapshot.is_dir()
    assert not receipt.exists()


def test_screen_failure_does_not_publish_applied_receipt(monkeypatch, tmp_path):
    profile_bytes = make_profile_bytes()
    profile_path = tmp_path / "profile.conf"
    profile_path.write_bytes(profile_bytes)
    config = make_contracted_config(profile_path.name, profile_bytes)
    receipt = tmp_path / "fased-runtime-profile.applied.json"
    receipt.write_text("stale\n", encoding="utf-8")
    fake_screen, marker = install_fake_screen(
        tmp_path, monkeypatch, exit_status=23
    )

    result = run_with_fake_screen(
        boot_command(config, monkeypatch), fake_screen, tmp_path
    )

    assert result.returncode == 23
    assert marker.is_file()
    assert not receipt.exists()


def test_contracted_preflight_removes_only_named_stale_outputs(
    monkeypatch, tmp_path
):
    profile_bytes = make_profile_bytes()
    profile_path = tmp_path / "profile.conf"
    profile_path.write_bytes(profile_bytes)
    config = make_contracted_config(profile_path.name, profile_bytes)
    stale_outputs = [tmp_path / "uartlog"] + [
        tmp_path / f"memory_stats{model_id}.csv" for model_id in range(5)
    ]
    for stale_output in stale_outputs:
        stale_output.write_text("stale\n", encoding="utf-8")
    untouched = tmp_path / "memory_stats5.csv"
    untouched.write_text("keep\n", encoding="utf-8")
    fake_screen, marker = install_fake_screen(tmp_path, monkeypatch)

    result = run_with_fake_screen(
        boot_command(config, monkeypatch), fake_screen, tmp_path
    )

    assert result.returncode == 0, result.stderr
    assert marker.is_file()
    assert all(not stale_output.exists() for stale_output in stale_outputs)
    assert untouched.read_text(encoding="utf-8") == "keep\n"


def test_profile_preflight_snapshots_exact_bytes_and_writes_exact_receipt(
    monkeypatch, tmp_path
):
    profile_bytes = make_profile_bytes()
    profile_path = tmp_path / "profile.conf"
    profile_path.write_bytes(profile_bytes)
    config = make_contracted_config(profile_path.name, profile_bytes)
    fake_screen, marker = install_fake_screen(tmp_path, monkeypatch)
    command = boot_command(config, monkeypatch)
    result = run_with_fake_screen(command, fake_screen, tmp_path)

    assert result.returncode == 0, result.stderr
    assert marker.is_file(), result.stderr
    screen_command = marker.read_text(encoding="utf-8")
    assert "-S fsim0" in screen_command
    assert "+mm_setting0_0=0" in screen_command
    assert screen_command.count("+mm_") == 140
    assert "$(sed" not in screen_command
    snapshot = tmp_path / config.fased_runtime_profile.snapshot_filename
    assert snapshot.is_file() and not snapshot.is_symlink()
    assert snapshot.read_bytes() == profile_bytes
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == (
        config.fased_runtime_profile.sha256
    )

    expected_receipt = {
        "hwdb_entry": config.name,
        "model_ids": list(config.fased_runtime_profile.model_ids),
        "profile_snapshot": config.fased_runtime_profile.snapshot_filename,
        "profile_source": config.fased_runtime_profile.filename,
        "settings_per_model": config.fased_runtime_profile.settings_per_model,
        "sha256": config.fased_runtime_profile.sha256,
        "total_settings": config.fased_runtime_profile.total_settings,
    }
    expected_receipt_bytes = (
        json.dumps(expected_receipt, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    receipt = tmp_path / "fased-runtime-profile.applied.json"
    assert receipt.read_bytes() == expected_receipt_bytes
    assert (
        f"[FASED] verified runtime profile sha256={config.fased_runtime_profile.sha256}"
        in result.stdout
    )


def artifact_contract(bitstream_bytes=b"bitstream", driver_bytes=b"driver"):
    return {
        "bitstream_tar": hashlib.sha256(bitstream_bytes).hexdigest(),
        "driver_tar": hashlib.sha256(driver_bytes).hexdigest(),
    }


def make_artifact_config(contract=None):
    return make_hwconfig(
        "runtime.conf",
        artifact_sha256=artifact_contract() if contract is None else contract,
        bitstream_tar="https://artifacts.example/firesim.tar.gz",
        driver_tar="https://artifacts.example/driver-bundle.tar.gz",
    )


def cache_path(tmp_path, uri):
    return tmp_path / URIContainer.hashed_name(uri)


def test_artifact_sha256_contract_is_parsed_exactly():
    contract = artifact_contract()
    config = make_artifact_config(contract)

    assert config.artifact_sha256 == ArtifactSHA256Contract(**contract)


@pytest.mark.parametrize(
    ("raw_contract", "message"),
    [
        ([], "must be a mapping"),
        ({"bitstream_tar": "0" * 64}, "fields must be exactly"),
        (
            {
                "bitstream_tar": "0" * 64,
                "driver_tar": "1" * 64,
                "extra": "2" * 64,
            },
            "fields must be exactly",
        ),
        (
            {"bitstream_tar": "A" * 64, "driver_tar": "1" * 64},
            "invalid bitstream_tar",
        ),
        (
            {
                "bitstream_tar": "__REPLACE_bad_SHA256__",
                "driver_tar": "1" * 64,
            },
            "invalid bitstream_tar",
        ),
    ],
)
def test_malformed_artifact_sha256_contract_is_rejected(raw_contract, message):
    with pytest.raises(ValueError, match=message):
        make_artifact_config(raw_contract)


def test_artifact_contract_requires_both_configured_uris():
    with pytest.raises(ValueError, match="requires bitstream_tar"):
        make_hwconfig(
            "runtime.conf",
            artifact_sha256=artifact_contract(),
            driver_tar="https://artifacts.example/driver-bundle.tar.gz",
        )


def test_explicit_null_artifact_contract_is_rejected():
    with pytest.raises(ValueError, match="artifact_sha256 must be a mapping"):
        RuntimeHWConfig(
            "test-hwdb-entry",
            {
                "custom_runtime_config": "runtime.conf",
                "bitstream_tar": "https://artifacts.example/firesim.tar.gz",
                "driver_tar": "https://artifacts.example/driver-bundle.tar.gz",
                "artifact_sha256": None,
            },
            "test-config-hwdb.yaml",
        )


def test_artifact_placeholder_parses_but_fetch_fails_before_download(
    monkeypatch, tmp_path
):
    config = make_hwconfig(
        "runtime.conf",
        artifact_sha256={
            "bitstream_tar": "__REPLACE_WITH_HBM_FIRESIM_TAR_GZ_SHA256__",
            "driver_tar": "__REPLACE_WITH_HBM_DRIVER_BUNDLE_TAR_GZ_SHA256__",
        },
        bitstream_tar="__REPLACE_WITH_HBM_FIRESIM_TAR_GZ_URI__",
        driver_tar="__REPLACE_WITH_HBM_DRIVER_BUNDLE_TAR_GZ_URI__",
    )
    monkeypatch.setattr(
        runtime_config,
        "downloadURI",
        lambda *_args: pytest.fail("an unresolved contract must not download"),
    )

    with pytest.raises(RuntimeError, match="unresolved bitstream_tar"):
        config.fetch_all_URI(str(tmp_path))


def test_wrong_same_uri_cache_is_rejected_without_redownload(monkeypatch, tmp_path):
    config = make_artifact_config()
    bitstream_cache = cache_path(tmp_path, config.bitstream_tar)
    bitstream_cache.write_bytes(b"stale bytes for the same URI")
    monkeypatch.setattr(
        runtime_config,
        "downloadURI",
        lambda *_args: pytest.fail("an existing contracted cache is not redownloaded"),
    )

    with pytest.raises(RuntimeError, match="bitstream_tar SHA-256 mismatch"):
        config.fetch_all_URI(str(tmp_path))


def test_downloaded_contracted_artifact_is_verified(monkeypatch, tmp_path):
    config = make_artifact_config()

    def write_wrong_bytes(_uri, destination):
        Path(destination).write_bytes(b"wrong download")

    monkeypatch.setattr(runtime_config, "downloadURI", write_wrong_bytes)

    with pytest.raises(RuntimeError, match="bitstream_tar SHA-256 mismatch"):
        config.fetch_all_URI(str(tmp_path))


@pytest.mark.parametrize("cache_kind", ["empty", "directory", "fifo", "symlink"])
def test_contracted_cache_must_be_nonempty_regular_nonsymlink(
    monkeypatch, tmp_path, cache_kind
):
    config = make_artifact_config()
    path = cache_path(tmp_path, config.bitstream_tar)
    if cache_kind == "empty":
        path.write_bytes(b"")
    elif cache_kind == "directory":
        path.mkdir()
    elif cache_kind == "fifo":
        os.mkfifo(path)
    else:
        target = tmp_path / "target"
        target.write_bytes(b"bitstream")
        path.symlink_to(target)
    monkeypatch.setattr(
        runtime_config,
        "downloadURI",
        lambda *_args: pytest.fail("an existing cache path must be validated"),
    )

    with pytest.raises(RuntimeError):
        config.fetch_all_URI(str(tmp_path))


def test_contracted_cache_is_rechecked_before_rsync(tmp_path):
    config = make_artifact_config()
    bitstream_cache = cache_path(tmp_path, config.bitstream_tar)
    driver_cache = cache_path(tmp_path, config.driver_tar)
    bitstream_cache.write_bytes(b"bitstream")
    driver_cache.write_bytes(b"driver")

    config.fetch_all_URI(str(tmp_path))
    bitstream_cache.write_bytes(b"changed after fetch")

    with pytest.raises(RuntimeError, match="bitstream_tar SHA-256 mismatch"):
        config.get_local_uri_paths(str(tmp_path))


def test_contracted_cache_must_be_readable(monkeypatch, tmp_path):
    config = make_artifact_config()
    bitstream_cache = cache_path(tmp_path, config.bitstream_tar)
    bitstream_cache.write_bytes(b"bitstream")
    real_open = runtime_config.os.open

    def deny_bitstream(path, flags):
        if path == str(bitstream_cache):
            raise PermissionError("mock unreadable artifact")
        return real_open(path, flags)

    monkeypatch.setattr(runtime_config.os, "open", deny_bitstream)

    with pytest.raises(RuntimeError, match="readable"):
        config.fetch_all_URI(str(tmp_path))


def test_contracted_cache_open_is_nofollow_and_nonblocking(monkeypatch, tmp_path):
    config = make_artifact_config()
    cache_path(tmp_path, config.bitstream_tar).write_bytes(b"bitstream")
    cache_path(tmp_path, config.driver_tar).write_bytes(b"driver")
    real_open = runtime_config.os.open
    observed_flags = []

    def record_open(path, flags):
        observed_flags.append(flags)
        return real_open(path, flags)

    monkeypatch.setattr(runtime_config.os, "open", record_open)

    config.fetch_all_URI(str(tmp_path))

    required_flags = os.O_NOFOLLOW | os.O_NONBLOCK
    assert observed_flags
    assert all(flags & required_flags == required_flags for flags in observed_flags)


def test_uncontracted_uri_cache_retains_generic_skip_behavior(monkeypatch, tmp_path):
    config = make_hwconfig(
        "runtime.conf",
        bitstream_tar="https://artifacts.example/firesim.tar.gz",
    )
    cache_path(tmp_path, config.bitstream_tar).write_bytes(b"generic cached bytes")
    monkeypatch.setattr(
        runtime_config,
        "downloadURI",
        lambda *_args: pytest.fail("generic existing cache should still be skipped"),
    )

    config.fetch_all_URI(str(tmp_path))
