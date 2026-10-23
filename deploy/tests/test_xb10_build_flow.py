from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest


DEPLOY_DIR = Path(__file__).resolve().parents[1]
FIRESIM_DIR = DEPLOY_DIR.parent
VIVADO_ENV_HELPER = (
    FIRESIM_DIR
    / "platforms"
    / "corigine_xb10"
    / "cl_firesim"
    / "scripts"
    / "vivado_env.sh"
)
BUILD_SCRIPT = FIRESIM_DIR / "platforms" / "corigine_xb10" / "build-bitstream.sh"

sys.path.insert(0, str(DEPLOY_DIR))
from buildtools.bitbuilder import CorigineXB10BitBuilder
from util.manager_ssh import get_manager_ssh_key_path


def test_manager_ssh_key_preserves_default(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    assert get_manager_ssh_key_path({}) == str(tmp_path / "firesim.pem")
    assert get_manager_ssh_key_path({"FIRESIM_SSH_KEY": ""}) == str(
        tmp_path / "firesim.pem"
    )


def test_manager_ssh_key_accepts_environment_override(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    assert get_manager_ssh_key_path(
        {"FIRESIM_SSH_KEY": "/scratch/build-auth/id_ed25519"}
    ) == "/scratch/build-auth/id_ed25519"
    assert get_manager_ssh_key_path(
        {"FIRESIM_SSH_KEY": "~/build-auth/id_ed25519"}
    ) == str(tmp_path / "build-auth" / "id_ed25519")


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        (None, ""),
        ({}, ""),
        (
            {"vivado_settings": "/ecad/tools/Xilinx Vivado/settings64.sh"},
            " --vivado-settings '/ecad/tools/Xilinx Vivado/settings64.sh'",
        ),
    ],
)
def test_xb10_bitbuilder_vivado_settings_argument(settings, expected):
    builder = CorigineXB10BitBuilder(None, settings)

    assert builder.get_build_script_extra_args() == expected


def test_xb10_bitbuilder_rejects_non_string_vivado_settings():
    with pytest.raises(ValueError, match="path string or null"):
        CorigineXB10BitBuilder(None, {"vivado_settings": 2025.1})


def make_fake_vivado(tmp_path: Path, version: str) -> Path:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_vivado = fake_bin / "vivado"
    fake_vivado.write_text(
        "#!/bin/bash\n"
        'if [ "${1:-}" = "-version" ]; then\n'
        f'    echo "vivado v{version} (64-bit)"\n'
        "fi\n",
        encoding="utf-8",
    )
    fake_vivado.chmod(0o755)
    return fake_bin


def run_vivado_activation(settings_path: str, environment):
    command = (
        f"source {shlex.quote(str(VIVADO_ENV_HELPER))}; "
        "firesim_xb10_activate_vivado "
        f"{shlex.quote(settings_path)} 2025.1"
    )
    return subprocess.run(
        ["/bin/bash", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_vivado_activation_sources_optional_settings(tmp_path):
    fake_bin = make_fake_vivado(tmp_path, "2025.1")
    settings = tmp_path / "settings64.sh"
    settings.write_text(
        f"export PATH={shlex.quote(str(fake_bin))}:/usr/bin:/bin\n",
        encoding="utf-8",
    )

    result = run_vivado_activation(
        str(settings), {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    )

    assert result.returncode == 0, result.stderr
    assert "Using Vivado 2025.1" in result.stdout


def test_vivado_activation_rejects_wrong_version(tmp_path):
    fake_bin = make_fake_vivado(tmp_path, "2024.1")

    result = run_vivado_activation(
        "", {"HOME": str(tmp_path), "PATH": f"{fake_bin}:/usr/bin:/bin"}
    )

    assert result.returncode != 0
    assert "requires Vivado 2025.1, found 2024.1" in result.stderr


def test_vivado_activation_rejects_missing_settings(tmp_path):
    result = run_vivado_activation(
        str(tmp_path / "missing-settings64.sh"),
        {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )

    assert result.returncode != 0
    assert "settings script is not readable" in result.stderr


def test_build_script_accepts_vivado_settings_without_real_vivado(tmp_path):
    fake_bin = make_fake_vivado(tmp_path, "2025.1")
    settings = tmp_path / "settings64.sh"
    settings.write_text(
        f"export PATH={shlex.quote(str(fake_bin))}:/usr/bin:/bin\n",
        encoding="utf-8",
    )
    cl_dir = tmp_path / "cl"
    scripts_dir = cl_dir / "scripts"
    scripts_dir.mkdir(parents=True)
    shutil.copy2(VIVADO_ENV_HELPER, scripts_dir / VIVADO_ENV_HELPER.name)

    result = subprocess.run(
        [
            "/bin/bash",
            str(BUILD_SCRIPT),
            "--cl_dir",
            str(cl_dir),
            "--frequency",
            "20",
            "--strategy",
            "TIMING",
            "--board",
            "xb10",
            "--vivado-settings",
            str(settings),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
    )

    assert result.returncode == 0, result.stderr
    assert "Using Vivado 2025.1" in result.stdout
