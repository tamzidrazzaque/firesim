""" This file manages the overall configuration of the system for running
simulation tasks. """

from __future__ import annotations

from dataclasses import dataclass
import re
from datetime import timedelta
from time import strftime, gmtime
import pprint
import logging
import yaml
import os
import sys
from fabric.operations import _stdoutString  # type: ignore
from fabric.api import prefix, settings, local, run  # type: ignore
from fabric.contrib.project import rsync_project  # type: ignore
from os.path import join as pjoin
from os.path import basename, expanduser
from pathlib import Path
from uuid import uuid1
from tempfile import TemporaryDirectory
import hashlib
import json
import shlex
import stat

from awstools.awstools import aws_resource_names
from awstools.afitools import (
    get_firesim_deploy_quintuplet_for_agfi,
    firesim_description_to_tags,
)
from runtools.firesim_topology_with_passes import FireSimTopologyWithPasses
from runtools.run_farm_deploy_managers import VitisInstanceDeployManager
from runtools.workload import WorkloadConfig
from runtools.run_farm import RunFarm
from runtools.simulation_data_classes import (
    TracerVConfig,
    AutoCounterConfig,
    HostDebugConfig,
    SynthPrintConfig,
    PartitionConfig,
)
from runtools.utils import is_on_aws
from util.inheritors import inheritors
from util.deepmerge import deep_merge
from util.streamlogger import InfoStreamLogger
from util.export import FIRESIM_BUILD_ENV_VARS, create_export_string
from util.targetprojectutils import extra_target_project_make_args, resolve_path
from buildtools.bitbuilder import get_deploy_dir
from util.io import downloadURI

from typing import Optional, Dict, Any, List, Sequence, Tuple, TYPE_CHECKING
import argparse  # this is not within a if TYPE_CHECKING: scope so the `register_task` in FireSim can evaluate it's annotation

if TYPE_CHECKING:
    from runtools.utils import MacAddress

LOCAL_DRIVERS_BASE = "../sim/output"
LOCAL_DRIVERS_GENERATED_SRC = "../sim/generated-src"
CUSTOM_RUNTIMECONFS_BASE = "../sim/custom-runtime-configs"

rootLogger = logging.getLogger()

# from  https://github.com/pandas-dev/pandas/blob/96b036cbcf7db5d3ba875aac28c4f6a678214bfb/pandas/io/common.py#L73
_RFC_3986_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+\-+.]*://")
_FASED_SETTING_PATTERN = re.compile(
    r"^\+mm_([A-Za-z][A-Za-z0-9_]*)_([0-9]+)=([0-9]+)$"
)
_FASED_CONTROLLED_EXTRA_TOKEN_PATTERN = re.compile(
    r"^[A-Za-z0-9_+.,:/=@%-]+$"
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ARTIFACT_SHA256_PLACEHOLDER_PATTERN = re.compile(
    r"^__REPLACE_WITH_[A-Z0-9]+(?:_[A-Z0-9]+)*_SHA256__$"
)


@dataclass(frozen=True)
class ArtifactSHA256Contract:
    """Expected hashes for the two externally supplied FPGA artifacts."""

    bitstream_tar: str
    driver_tar: str


@dataclass(frozen=True)
class FASEDRuntimeProfile:
    """A validated, content-addressed FASED runtime-profile contract."""

    filename: str
    sha256: str
    model_ids: Tuple[int, ...]
    settings_per_model: int

    @property
    def total_settings(self) -> int:
        return len(self.model_ids) * self.settings_per_model

    @property
    def snapshot_filename(self) -> str:
        return f".fased-runtime-profile-{self.sha256}.conf"


class URIContainer:
    """A class which contains the details for downloading a single URI."""

    """a property name on RuntimeHWConfig"""
    hwcfg_prop: str
    """ the final filename inside sim_slot_x, this is a filename, not a path"""
    destination_name: str

    def __init__(self, hwcfg_prop: str, destination_name: str):
        self.hwcfg_prop = hwcfg_prop
        self.destination_name = destination_name

    # this filename will be used when pre-downloading
    @classmethod
    def hashed_name(cls, uri: str) -> str:
        m = hashlib.sha256()
        m.update(bytes(uri, "utf-8"))
        return m.hexdigest()

    def _resolve_vanilla_path(self, hwcfg: RuntimeHWConfig) -> Optional[str]:
        """Allows fallback to a vanilla path. Relative paths are resolved relative to firesim/deploy/.
        This will convert a vanilla path to a URI, or return None."""
        uri: Optional[str] = getattr(hwcfg, self.hwcfg_prop)

        # do nothing if there isn't a URI
        if uri is None:
            return None

        # if already a URI, exit early returning unmodified string
        is_uri = re.match(_RFC_3986_PATTERN, uri)
        if is_uri:
            return uri

        # expanduser() is required to get ~ home directory expansion working
        # relative paths are relative to firesim/deploy
        expanded = Path(expanduser(uri))

        try:
            # strict=True will throw if the file doesn't exist
            resolved = expanded.resolve(strict=True)
        except FileNotFoundError as e:
            raise Exception(
                f"{self.hwcfg_prop} file fallback at path '{uri}' or '{expanded}' was not found"
            )

        return f"file://{resolved}"

    def _choose_path(
        self, local_dir: str, hwcfg: RuntimeHWConfig
    ) -> Optional[Tuple[str, str]]:
        """Return a deterministic path, given a parent folder and a RuntimeHWConfig object. The URI
        as generated from hwcfg is also returned."""
        uri: Optional[str] = self._resolve_vanilla_path(hwcfg)

        # do nothing if there isn't a URI
        if uri is None:
            return None

        # choose a repeatable, path based on the hash of the URI
        destination = pjoin(local_dir, self.hashed_name(uri))

        return (uri, destination)

    def _expected_sha256(self, hwcfg: RuntimeHWConfig) -> Optional[str]:
        contract = getattr(hwcfg, "artifact_sha256", None)
        if contract is None:
            return None
        expected_sha256 = getattr(contract, self.hwcfg_prop)
        if _SHA256_PATTERN.fullmatch(expected_sha256) is None:
            raise RuntimeError(
                f"HWDB entry {hwcfg.name} has an unresolved {self.hwcfg_prop} "
                "SHA-256 placeholder"
            )
        return expected_sha256

    def verify_local_artifact(self, destination: str, hwcfg: RuntimeHWConfig) -> None:
        """Fail closed if a contracted cache entry is not the expected file."""
        expected_sha256 = self._expected_sha256(hwcfg)
        if expected_sha256 is None:
            return

        fd: Optional[int] = None
        digest = hashlib.sha256()
        try:
            path_metadata = os.lstat(destination)
            if stat.S_ISLNK(path_metadata.st_mode):
                raise RuntimeError(
                    f"Contracted {self.hwcfg_prop} cache path is a symlink: "
                    f"{destination}"
                )
            if not stat.S_ISREG(path_metadata.st_mode):
                raise RuntimeError(
                    f"Contracted {self.hwcfg_prop} cache path is not a regular file: "
                    f"{destination}"
                )
            flags = (
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0)
            )
            fd = os.open(destination, flags)
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise RuntimeError(
                    f"Contracted {self.hwcfg_prop} cache path is not a regular file: "
                    f"{destination}"
                )
            if metadata.st_size == 0:
                raise RuntimeError(
                    f"Contracted {self.hwcfg_prop} cache file is empty: {destination}"
                )
            with os.fdopen(fd, "rb") as artifact:
                fd = None
                for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as error:
            raise RuntimeError(
                f"Contracted {self.hwcfg_prop} cache path must be a readable, "
                f"regular, non-symlink file: {destination}: {error}"
            ) from error
        finally:
            if fd is not None:
                os.close(fd)

        actual_sha256 = digest.hexdigest()
        if actual_sha256 != expected_sha256:
            raise RuntimeError(
                f"Contracted {self.hwcfg_prop} SHA-256 mismatch for {destination}: "
                f"expected {expected_sha256}, got {actual_sha256}"
            )

    def local_pre_download(
        self, local_dir: str, hwcfg: RuntimeHWConfig
    ) -> Optional[Tuple[str, str]]:
        """Cached download of the URI contained in this class to a user-specified
        destination folder. The destination name is a SHA256 hash of the URI.
        If the file exists this will NOT overwrite."""

        # Reject unresolved hash placeholders before URI resolution, network,
        # or filesystem mutation.
        contracted = self._expected_sha256(hwcfg) is not None

        # resolve the URI and the path '/{dir}/{hash}' we should download to
        both = self._choose_path(local_dir, hwcfg)

        # do nothing if there isn't a URI
        if both is None:
            return None

        (uri, destination) = both

        # When it exists, return the same information, but skip the download
        destination_exists = (
            os.path.lexists(destination) if contracted else Path(destination).exists()
        )
        if destination_exists:
            self.verify_local_artifact(destination, hwcfg)
            rootLogger.debug(f"Skipping download of uri: '{uri}'")
            return (uri, destination)

        try:
            downloadURI(uri, destination)
        except FileNotFoundError as e:
            raise Exception(f"{self.hwcfg_prop} path '{uri}' was not found")

        self.verify_local_artifact(destination, hwcfg)

        # return, this is not passed to rsync
        return (uri, destination)

    def get_rsync_path(
        self, local_dir: str, hwcfg: RuntimeHWConfig
    ) -> Optional[Tuple[str, str]]:
        """Does not download. Returns the rsync path required to send an already downloaded
        URI to the runhost."""

        # Fail on an unresolved hash before resolving or using its URI.
        self._expected_sha256(hwcfg)

        # resolve the URI and the path '/{dir}/{hash}' we should download to
        both = self._choose_path(local_dir, hwcfg)

        # do nothing if there isn't a URI
        if both is None:
            return None

        (uri, destination) = both

        # Revalidate immediately before handing this path to the rsync caller.
        # The XB10 remote side independently checks the received bytes again.
        self.verify_local_artifact(destination, hwcfg)

        # because the local file has a nonsense name (the hash)
        # we are required to specify the destination name to rsync
        return (destination, self.destination_name)


class RuntimeHWConfig:
    """A pythonic version of the entires in config_hwdb.yaml"""

    name: str
    platform: Optional[str]

    hwdb_file: str

    # TODO: should be abstracted out between platforms with a URI
    agfi: Optional[str]
    """User-specified, URI path to bitstream tar file"""
    bitstream_tar: Optional[str]

    deploy_quintuplet: Optional[str]
    deploy_makefrag: Optional[str]
    customruntimeconfig: str
    # note whether we've built a copy of the simulation driver for this hwconf
    driver_built: bool
    tarball_built: bool
    additional_required_files: List[Tuple[str, str]]
    driver_name_prefix: str
    local_driver_base_dir: str
    driver_type_message: str
    """User-specified, URI path to driver tarball"""
    driver_tar: Optional[str]
    fased_runtime_profile: Optional[FASEDRuntimeProfile]
    artifact_sha256: Optional[ArtifactSHA256Contract]

    """ A list of URIContainer objects, one for each URI that is able to be specified """
    uri_list: list[URIContainer]

    # Members that are initialized here also need to be initialized in
    # RuntimeBuildRecipeConfig.__init__
    def __init__(
        self, name: str, hwconfig_dict: Dict[str, Any], hwdb_file: str
    ) -> None:
        self.name = name

        self.hwdb_file = hwdb_file

        if sum(["agfi" in hwconfig_dict, "bitstream_tar" in hwconfig_dict]) > 1:
            raise Exception(
                f"Must only have 'agfi' or 'bitstream_tar' HWDB entry {name}."
            )

        self.agfi = hwconfig_dict.get("agfi")
        self.bitstream_tar = hwconfig_dict.get("bitstream_tar")
        self.driver_tar = hwconfig_dict.get("driver_tar")

        self.platform = None
        self.driver_built = False
        self.tarball_built = False
        self.additional_required_files = []
        self.driver_name_prefix = ""
        self.driver_type_message = "FPGA software"
        self.local_driver_base_dir = LOCAL_DRIVERS_BASE

        self.uri_list = []

        if self.agfi is not None:
            self.platform = "f2"
        else:
            self.uri_list.append(
                URIContainer("bitstream_tar", self.get_bitstream_tar_filename())
            )

        if (
            "deploy_triplet_override" in hwconfig_dict.keys()
            and "deploy_quintuplet_override" in hwconfig_dict.keys()
        ):
            rootLogger.error(
                "Cannot have both 'deploy_quintuplet_override' and 'deploy_triplet_override' in hwdb entry. Define only 'deploy_quintuplet_override'."
            )
            sys.exit(1)
        elif "deploy_triplet_override" in hwconfig_dict.keys():
            rootLogger.warning(
                "Please rename your 'deploy_triplet_override' key in your hwdb entry to 'deploy_quintuplet_override'. Support for 'deploy_triplet_override' will be removed in the future."
            )

        hwconfig_override_build_quintuplet = hwconfig_dict.get(
            "deploy_quintuplet_override"
        )
        if hwconfig_override_build_quintuplet is None:
            # temporary backwards compat for old key
            hwconfig_override_build_quintuplet = hwconfig_dict.get(
                "deploy_triplet_override"
            )

        if (
            hwconfig_override_build_quintuplet is not None
            and len(hwconfig_override_build_quintuplet.split("-")) == 3
        ):
            # convert old build_triplet into buildquintuplet
            hwconfig_override_build_quintuplet = (
                "f2-firesim-" + hwconfig_override_build_quintuplet
            )

        self.deploy_quintuplet = hwconfig_override_build_quintuplet
        if self.deploy_quintuplet is not None:
            rootLogger.warning(
                f"{name} is overriding a deploy quintuplet in your config_hwdb.yaml file. Make sure you understand why!"
            )

        hwconfig_override_build_makefrag = hwconfig_dict.get("deploy_makefrag_override")
        self.deploy_makefrag = hwconfig_override_build_makefrag
        if self.deploy_makefrag is not None:
            rootLogger.warning(
                f"{name} is overriding a deploy makefrag in your config_hwdb.yaml file. Make sure you understand why!"
            )

        self.customruntimeconfig = hwconfig_dict["custom_runtime_config"]
        self.fased_runtime_profile = (
            self._load_fased_runtime_profile(hwconfig_dict["fased_runtime_profile"])
            if "fased_runtime_profile" in hwconfig_dict
            else None
        )
        self.artifact_sha256 = (
            self._load_artifact_sha256(hwconfig_dict["artifact_sha256"])
            if "artifact_sha256" in hwconfig_dict
            else None
        )

        self.additional_required_files = []

        self.uri_list.append(URIContainer("driver_tar", self.get_driver_tar_filename()))
        rootLogger.debug(f"RuntimeHWConfig self.platform {self.platform}")

    def _load_artifact_sha256(self, raw_contract: Any) -> ArtifactSHA256Contract:
        """Validate exact bitstream/driver artifact hashes from an HWDB entry."""
        if not isinstance(raw_contract, dict):
            raise ValueError(
                f"HWDB entry {self.name} artifact_sha256 must be a mapping"
            )

        required_fields = {"bitstream_tar", "driver_tar"}
        actual_fields = set(raw_contract)
        if actual_fields != required_fields:
            raise ValueError(
                f"HWDB entry {self.name} artifact_sha256 fields must be exactly "
                f"{sorted(required_fields)}; got {sorted(actual_fields)}"
            )

        values: Dict[str, str] = {}
        for field in sorted(required_fields):
            value = raw_contract[field]
            is_hash = isinstance(value, str) and _SHA256_PATTERN.fullmatch(value)
            is_placeholder = isinstance(
                value, str
            ) and _ARTIFACT_SHA256_PLACEHOLDER_PATTERN.fullmatch(value)
            if not is_hash and not is_placeholder:
                raise ValueError(
                    f"HWDB entry {self.name} has an invalid {field} artifact SHA-256"
                )
            configured_uri = getattr(self, field)
            if not isinstance(configured_uri, str) or not configured_uri:
                raise ValueError(
                    f"HWDB entry {self.name} artifact_sha256 requires {field}"
                )
            values[field] = value

        return ArtifactSHA256Contract(**values)

    def _load_fased_runtime_profile(
        self, raw_contract: Any
    ) -> FASEDRuntimeProfile:
        """Validate a controlled FASED profile and bind it to its exact bytes."""
        if not isinstance(raw_contract, dict):
            raise ValueError(
                f"HWDB entry {self.name} fased_runtime_profile must be a mapping"
            )

        required_fields = {"sha256", "model_ids", "settings_per_model"}
        actual_fields = set(raw_contract)
        if actual_fields != required_fields:
            raise ValueError(
                f"HWDB entry {self.name} fased_runtime_profile fields must be "
                f"exactly {sorted(required_fields)}; got {sorted(actual_fields)}"
            )

        expected_sha256 = raw_contract["sha256"]
        if not isinstance(expected_sha256, str) or re.fullmatch(
            r"[0-9a-f]{64}", expected_sha256
        ) is None:
            raise ValueError(
                f"HWDB entry {self.name} has an invalid FASED profile SHA-256"
            )

        raw_model_ids = raw_contract["model_ids"]
        if not isinstance(raw_model_ids, list) or any(
            type(model_id) is not int for model_id in raw_model_ids
        ):
            raise ValueError(
                f"HWDB entry {self.name} FASED model_ids must be an integer list"
            )
        model_ids = tuple(raw_model_ids)
        if model_ids != (0, 1, 2, 3, 4):
            raise ValueError(
                f"HWDB entry {self.name} FASED model_ids must be exactly [0, 1, 2, 3, 4]"
            )

        settings_per_model = raw_contract["settings_per_model"]
        if type(settings_per_model) is not int or settings_per_model not in (28, 34):
            raise ValueError(
                f"HWDB entry {self.name} FASED settings_per_model must be 28 or 34"
            )

        filename = self.customruntimeconfig
        if (
            not isinstance(filename, str)
            or not filename
            or filename in (".", "..")
            or filename != os.path.basename(filename)
            or "/" in filename
            or "\\" in filename
        ):
            raise ValueError(
                f"HWDB entry {self.name} contracted custom_runtime_config must be a safe bare filename"
            )

        configured_path = Path(self.get_local_runtime_conf_path())
        if not configured_path.is_absolute():
            deploy_dir = Path(__file__).resolve().parents[1]
            configured_path = deploy_dir / configured_path
        if configured_path.is_symlink():
            raise ValueError(
                f"HWDB entry {self.name} FASED profile must not be a symlink: {configured_path}"
            )
        if not configured_path.is_file() or not os.access(configured_path, os.R_OK):
            raise ValueError(
                f"HWDB entry {self.name} FASED profile is missing, unreadable, or not a regular file: {configured_path}"
            )

        profile_bytes = configured_path.read_bytes()
        if not profile_bytes:
            raise ValueError(
                f"HWDB entry {self.name} FASED profile is empty: {configured_path}"
            )
        actual_sha256 = hashlib.sha256(profile_bytes).hexdigest()
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"HWDB entry {self.name} FASED profile SHA-256 mismatch: "
                f"expected {expected_sha256}, got {actual_sha256}"
            )

        try:
            profile_text = profile_bytes.decode("ascii")
        except UnicodeDecodeError as error:
            raise ValueError(
                f"HWDB entry {self.name} FASED profile must be ASCII"
            ) from error
        if "\r" in profile_text:
            raise ValueError(
                f"HWDB entry {self.name} FASED profile must use LF line endings"
            )
        # Split only on the LF byte that the launch-time sed command flattens.
        # Python's splitlines() also treats VT, FF, and record separators as
        # line boundaries, which would validate bytes the driver receives as
        # one malformed argument.
        lines = profile_text.split("\n")
        if lines[-1] == "":
            lines.pop()

        settings_by_model: Dict[int, Dict[str, int]] = {
            model_id: {} for model_id in model_ids
        }
        for line_number, line in enumerate(lines, start=1):
            match = _FASED_SETTING_PATTERN.fullmatch(line)
            if match is None:
                raise ValueError(
                    f"HWDB entry {self.name} FASED profile line {line_number} "
                    "must be +mm_<setting>_<model>=<nonnegative integer>"
                )
            setting_name, model_text, value_text = match.groups()
            model_id = int(model_text)
            if model_text != str(model_id):
                raise ValueError(
                    f"HWDB entry {self.name} FASED profile line {line_number} "
                    f"has noncanonical model id {model_text}"
                )
            if model_id not in settings_by_model:
                raise ValueError(
                    f"HWDB entry {self.name} FASED profile has unexpected model {model_id}"
                )
            if setting_name in settings_by_model[model_id]:
                raise ValueError(
                    f"HWDB entry {self.name} FASED profile duplicates "
                    f"model {model_id} setting {setting_name}"
                )
            value = int(value_text)
            if value > 0xFFFFFFFF:
                raise ValueError(
                    f"HWDB entry {self.name} FASED profile line {line_number} "
                    f"value exceeds UINT32_MAX"
                )
            settings_by_model[model_id][setting_name] = value

        for model_id, settings in settings_by_model.items():
            if len(settings) != settings_per_model:
                raise ValueError(
                    f"HWDB entry {self.name} FASED model {model_id} has "
                    f"{len(settings)} settings; expected {settings_per_model}"
                )
        reference_settings = settings_by_model[model_ids[0]]
        for model_id in model_ids[1:]:
            if settings_by_model[model_id] != reference_settings:
                raise ValueError(
                    f"HWDB entry {self.name} FASED model {model_id} settings "
                    "do not exactly match model 0"
                )

        return FASEDRuntimeProfile(
            filename=filename,
            sha256=expected_sha256,
            model_ids=model_ids,
            settings_per_model=settings_per_model,
        )

    def _sanitize_fased_controlled_extra_args(
        self, raw_args: str, channel: str
    ) -> str:
        """Return shell-quoted inert tokens for a contracted launch channel."""
        if not isinstance(raw_args, str):
            raise ValueError(
                f"HWDB entry {self.name} {channel} must be a string for a "
                "contracted FASED launch"
            )
        if re.fullmatch(r"[A-Za-z0-9_+.,:/=@% \t-]*", raw_args) is None:
            raise ValueError(
                f"HWDB entry {self.name} {channel} contains an unsafe shell "
                "character for a contracted FASED launch"
            )
        try:
            tokens = shlex.split(raw_args, posix=True)
        except ValueError as error:
            raise ValueError(
                f"HWDB entry {self.name} {channel} is not valid inert-token syntax"
            ) from error
        for token in tokens:
            if _FASED_CONTROLLED_EXTRA_TOKEN_PATTERN.fullmatch(token) is None:
                raise ValueError(
                    f"HWDB entry {self.name} {channel} contains unsafe token "
                    f"{token!r}"
                )
            if "+mm_" in token:
                raise ValueError(
                    f"HWDB entry {self.name} forbids out-of-band +mm_ arguments "
                    f"in {channel} when fased_runtime_profile is contracted"
                )
        return " ".join(shlex.quote(token) for token in tokens)

    def _sanitize_fased_controlled_generated_tokens(
        self,
        tokens: Sequence[str],
        channel: str,
        *,
        allowed_expansions: Tuple[str, ...] = (),
    ) -> List[str]:
        """Validate and quote every generated token in a contracted launch."""
        sanitized = []
        for token in tokens:
            if not token:
                continue
            if token in allowed_expansions:
                sanitized.append(token)
                continue
            if (
                not isinstance(token, str)
                or _FASED_CONTROLLED_EXTRA_TOKEN_PATTERN.fullmatch(token) is None
            ):
                raise ValueError(
                    f"HWDB entry {self.name} {channel} contains unsafe generated "
                    f"token {token!r}"
                )
            if "+mm_" in token:
                raise ValueError(
                    f"HWDB entry {self.name} forbids out-of-band +mm_ arguments "
                    f"in {channel} when fased_runtime_profile is contracted"
                )
            sanitized.append(shlex.quote(token))
        return sanitized

    def _get_fased_runtime_profile_commands(self) -> Tuple[str, str]:
        """Return fail-closed prelaunch and receipt-publication commands."""
        profile = self.fased_runtime_profile
        if profile is None:
            return ("", "")

        receipt_filename = "fased-runtime-profile.applied.json"
        receipt = {
            "hwdb_entry": self.name,
            "model_ids": list(profile.model_ids),
            "profile_snapshot": profile.snapshot_filename,
            "profile_source": profile.filename,
            "settings_per_model": profile.settings_per_model,
            "sha256": profile.sha256,
            "total_settings": profile.total_settings,
        }
        receipt_json = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
        model_ids_text = ",".join(map(str, profile.model_ids))

        prelaunch = "\n".join(
            [
                "set -euo pipefail",
                f"fased_profile_source={shlex.quote(profile.filename)}",
                f"fased_profile_snapshot={shlex.quote(profile.snapshot_filename)}",
                f"fased_profile_expected_sha={shlex.quote(profile.sha256)}",
                f"fased_profile_receipt={shlex.quote(receipt_filename)}",
                'fased_profile_tmp="${fased_profile_snapshot}.tmp.$$"',
                'fased_receipt_tmp="${fased_profile_receipt}.tmp.$$"',
                "fased_profile_cleanup() {",
                '  rm -f -- "$fased_profile_tmp" "$fased_receipt_tmp"',
                "}",
                "trap fased_profile_cleanup EXIT",
                'rm -f -- "$fased_profile_receipt" "$fased_profile_tmp" '
                '"$fased_receipt_tmp" uartlog memory_stats0.csv memory_stats1.csv '
                "memory_stats2.csv memory_stats3.csv memory_stats4.csv",
                '[[ -f "$fased_profile_source" && ! -L "$fased_profile_source" && -r "$fased_profile_source" && -s "$fased_profile_source" ]]',
                'cp -- "$fased_profile_source" "$fased_profile_tmp"',
                'fased_profile_actual_sha="$(sha256sum -- "$fased_profile_tmp" | awk \'{print $1}\')"',
                '[[ "$fased_profile_actual_sha" == "$fased_profile_expected_sha" ]]',
                'if [[ -e "$fased_profile_snapshot" || -L "$fased_profile_snapshot" ]]; then',
                '  if [[ ! -f "$fased_profile_snapshot" || -L "$fased_profile_snapshot" ]]; then',
                "    printf '[FASED] invalid runtime profile snapshot path: %s\\n' "
                '"$fased_profile_snapshot" >&2',
                "    exit 1",
                "  fi",
                "fi",
                'mv -fT -- "$fased_profile_tmp" "$fased_profile_snapshot"',
                '[[ -f "$fased_profile_snapshot" && ! -L "$fased_profile_snapshot" && -r "$fased_profile_snapshot" && -s "$fased_profile_snapshot" ]]',
                'fased_profile_snapshot_sha="$(sha256sum -- "$fased_profile_snapshot" | awk \'{print $1}\')"',
                '[[ "$fased_profile_snapshot_sha" == "$fased_profile_expected_sha" ]]',
                'fased_profile_args="$(sed \':a;N;$!ba;s/\\n/ /g\' -- "$fased_profile_snapshot")"',
                '[[ -n "$fased_profile_args" ]]',
                f"printf '%s\\n' {shlex.quote(receipt_json)} > \"$fased_receipt_tmp\"",
            ]
        )
        postlaunch = "\n".join(
            [
                'mv -fT -- "$fased_receipt_tmp" "$fased_profile_receipt"',
                '[[ -f "$fased_profile_receipt" && ! -L "$fased_profile_receipt" && -r "$fased_profile_receipt" && -s "$fased_profile_receipt" ]]',
                "trap - EXIT",
                'printf \'[FASED] verified runtime profile sha256=%s models=%s settings_per_model=%s total=%s\\n\' '
                f'"$fased_profile_actual_sha" {shlex.quote(model_ids_text)} '
                f"{profile.settings_per_model} {profile.total_settings}",
            ]
        )
        return (prelaunch, postlaunch)

    def get_deploytriplet_for_config(self) -> str:
        """Get the deploytriplet for this configuration."""
        quin = self.get_deployquintuplet_for_config()
        return "-".join(quin.split("-")[2:])

    @classmethod
    def get_driver_tar_filename(cls) -> str:
        """Get the name of the tarball inside the sim_slot_X directory on the run host."""
        return "driver-bundle.tar.gz"

    @classmethod
    def get_bitstream_tar_filename(cls) -> str:
        """Get the name of the bit tar file inside the sim_slot_X directory on the run host."""
        return "firesim.tar.gz"

    def get_platform(self) -> str:
        assert self.platform is not None
        return self.platform

    def get_driver_name_suffix(self) -> str:
        return "-" + self.get_platform()

    def get_driver_build_target(self) -> str:
        return self.get_platform()

    def set_check(self, lhs: Optional[str], rhs: str, name: str) -> None:
        if lhs is not None:
            assert (
                lhs == rhs
            ), f"{name} is already set to {lhs} (cannot set it to {rhs})"
        return

    def set_platform(self, platform: str) -> None:
        self.set_check(self.platform, platform, "platform")
        self.platform = platform

    def set_deploy_quintuplet(self, deploy_quintuplet: str) -> None:
        self.set_check(self.deploy_quintuplet, deploy_quintuplet, "deploy_quintuplet")
        self.deploy_quintuplet = deploy_quintuplet

    def set_deploy_makefrag(self, deploy_makefrag: Optional[str]) -> None:
        if self.deploy_makefrag is not None:
            # self.deploy_makefrag comes from the override and thus takes precedent (can't override)
            return
        # otherwise, you can override from deploy_makefrag (which should come from metadata)
        self.deploy_makefrag = deploy_makefrag

    def get_deployquintuplet_for_config(self) -> str:
        """Get the deployquintuplet for this configuration. This memoizes the request
        to the AWS AGFI API."""
        rootLogger.debug(
            f"get_deployquintuplet_for_config {self.deploy_quintuplet} {self.get_platform}"
        )
        if self.deploy_quintuplet is not None:
            return self.deploy_quintuplet

        if self.get_platform() == "f2":
            rootLogger.debug(
                "Setting deployquintuplet by querying the AGFI's description."
            )
            self.deploy_quintuplet = get_firesim_deploy_quintuplet_for_agfi(self.agfi)
        else:
            assert False, "Unable to obtain deploy_quintuplet"

        return self.deploy_quintuplet

    def get_deployquintuplet_pieces_for_config(self) -> List[str]:
        return self.get_deployquintuplet_for_config().split("-")

    def get_deploymakefrag_for_config(self) -> Optional[str]:
        if self.deploy_makefrag:
            base = self.hwdb_file
            abs_deploy_makefrag = resolve_path(self.deploy_makefrag, base)
            if abs_deploy_makefrag is None:
                raise Exception(
                    f"Unable to find deploy_makefrag ({self.deploy_makefrag}) either as an absolute path or relative to {base}"
                )
            else:
                self.deploy_makefrag = abs_deploy_makefrag

        return self.deploy_makefrag

    def get_design_name(self) -> str:
        """Returns the name used to prefix MIDAS-emitted files. (The DESIGN make var)"""
        return self.get_deployquintuplet_pieces_for_config()[2]

    def get_local_driver_binaryname(self) -> str:
        """Get the name of the driver binary."""
        return (
            self.driver_name_prefix
            + self.get_design_name()
            + self.get_driver_name_suffix()
        )

    def get_local_driver_dir(self) -> str:
        """Get the relative local directory that contains the driver used to
        run this sim."""
        rootLogger.info(
            f"get_local_driver_dir {self.get_deployquintuplet_for_config()}"
        )
        return (
            self.local_driver_base_dir
            + "/"
            + self.get_platform()
            + "/"
            + self.get_deployquintuplet_for_config()
            + "/"
        )

    def get_local_driver_path(self) -> str:
        """return relative local path of the driver used to run this sim."""
        return self.get_local_driver_dir() + self.get_local_driver_binaryname()

    def local_quintuplet_path(self) -> Path:
        """return the local path of the quintuplet folder. the tarball that is created goes inside this folder"""
        quintuplet = self.get_deployquintuplet_for_config()
        return (
            Path(get_deploy_dir()) / "../sim/output" / self.get_platform() / quintuplet
        )

    def local_tarball_path(self, name: str) -> Path:
        """return the local path of the tarball"""
        return self.local_quintuplet_path() / name

    def get_local_runtimeconf_binaryname(self) -> str:
        """Get the name of the runtimeconf file."""
        if self.customruntimeconfig is None:
            return None
        return os.path.basename(self.customruntimeconfig)

    def get_local_runtime_conf_path(self) -> str:
        """return relative local path of the runtime conf used to run this sim."""
        if self.customruntimeconfig is None:
            return None
        return os.path.join(
            CUSTOM_RUNTIMECONFS_BASE, self.customruntimeconfig.lstrip("/")
        )

    def get_additional_required_sim_files(self) -> List[Tuple[str, str]]:
        """return list of any additional files required to run a simulation."""
        return self.additional_required_files

    def get_boot_simulation_command(
        self,
        slotid: int,
        all_macs: Sequence[MacAddress],
        all_rootfses: Sequence[Optional[str]],
        all_linklatencies: Sequence[int],
        all_netbws: Sequence[int],
        profile_interval: int,
        all_bootbinaries: List[str],
        all_shmemportnames: List[str],
        tracerv_config: TracerVConfig,
        autocounter_config: AutoCounterConfig,
        hostdebug_config: HostDebugConfig,
        synthprint_config: SynthPrintConfig,
        partition_config: PartitionConfig,
        cutbridge_idxs: List[int],
        extra_plusargs: str,
        extra_args: str,
    ) -> str:
        """return the command used to boot the simulation. this has to have
        some external params passed to it, because not everything is contained
        in a runtimehwconfig. TODO: maybe runtimehwconfig should be renamed to
        pre-built runtime config? It kinda contains a mix of pre-built and
        runtime parameters currently."""

        # TODO: supernode support
        tracefile = "+tracefile=TRACEFILE" if tracerv_config.enable else ""
        autocounterfile = "+autocounter-filename-base=AUTOCOUNTERFILE"

        # this monstrosity boots the simulator, inside screen, inside script
        # the sed is in there to get rid of newlines in runtime confs
        driver = self.get_local_driver_binaryname()
        runtimeconf = self.get_local_runtimeconf_binaryname()
        profile_preflight = ""
        profile_postlaunch = ""
        extra_plusargs_for_command = extra_plusargs
        extra_args_for_command = extra_args
        if self.fased_runtime_profile is not None:
            extra_plusargs_for_command = self._sanitize_fased_controlled_extra_args(
                extra_plusargs, "extra_plusargs"
            )
            extra_args_for_command = self._sanitize_fased_controlled_extra_args(
                extra_args, "extra_args"
            )
            profile_preflight, profile_postlaunch = (
                self._get_fased_runtime_profile_commands()
            )

        def array_to_plusargs(
            valuesarr: Sequence[Optional[Any]], plusarg: str
        ) -> List[str]:
            args = []
            for index, arg in enumerate(valuesarr):
                if arg is not None:
                    args.append("""{}{}={}""".format(plusarg, index, arg))
            return args

        def array_to_lognames(
            values: Sequence[Optional[Any]], prefix: str
        ) -> List[str]:
            names = [
                "{}{}".format(prefix, i) if val is not None else None
                for (i, val) in enumerate(values)
            ]
            return array_to_plusargs(names, "+" + prefix)

        command_macs = array_to_plusargs(all_macs, "+macaddr")
        command_rootfses = array_to_plusargs(all_rootfses, "+blkdev")
        command_linklatencies = array_to_plusargs(all_linklatencies, "+linklatency")
        command_netbws = array_to_plusargs(all_netbws, "+netbw")
        command_shmemportnames = array_to_plusargs(all_shmemportnames, "+shmemportname")

        command_niclogs = array_to_lognames(all_macs, "niclog")
        command_blkdev_logs = array_to_lognames(all_rootfses, "blkdev-log")

        command_bootbinaries = array_to_plusargs(all_bootbinaries, "+prog")
        zero_out_dram = "+zero-out-dram" if (hostdebug_config.zero_out_dram) else ""
        disable_asserts = (
            "+disable-asserts" if (hostdebug_config.disable_synth_asserts) else ""
        )
        print_cycle_prefix = (
            "+print-no-cycle-prefix" if not synthprint_config.cycle_prefix else ""
        )

        # TODO supernode support
        dwarf_file_name = "+dwarf-file-name=" + all_bootbinaries[0] + "-dwarf"

        need_sudo = "sudo" if is_on_aws() else ""

        screen_name = "fsim{}".format(slotid)

        # TODO: supernode support (tracefile, trace-select.. etc)
        permissive_driver_args = []
        if self.fased_runtime_profile is not None:
            permissive_driver_args += ["$fased_profile_args"]
        elif runtimeconf:
            permissive_driver_args += [
                f"$(sed ':a;N;$!ba;s/\\n/ /g' {runtimeconf})"
            ]
        if profile_interval != -1:
            permissive_driver_args += [f"+profile-interval={profile_interval}"]
        permissive_driver_args += [zero_out_dram]
        permissive_driver_args += [disable_asserts]
        permissive_driver_args += command_macs
        permissive_driver_args += command_rootfses
        permissive_driver_args += command_niclogs
        permissive_driver_args += command_blkdev_logs
        permissive_driver_args += [
            f"{tracefile}",
            f"+trace-select={tracerv_config.select}",
            f"+trace-start={tracerv_config.start}",
            f"+trace-end={tracerv_config.end}",
            f"+trace-output-format={tracerv_config.output_format}",
            dwarf_file_name,
        ]
        permissive_driver_args += [
            f"+autocounter-readrate={autocounter_config.readrate}",
            autocounterfile,
        ]
        permissive_driver_args += [
            print_cycle_prefix,
            f"+print-start={synthprint_config.start}",
            f"+print-end={synthprint_config.end}",
        ]
        permissive_driver_args += command_linklatencies
        permissive_driver_args += command_netbws
        permissive_driver_args += command_shmemportnames

        if partition_config.is_partitioned():
            assert partition_config.node is not None

            # For QSFP metasims, assume that the partitions are connected in a ring-topology.
            # Then, when you know your FPGA idx & the total number of FPGAs, you know
            # your lhs & rhs neighbors to communicate with.
            permissive_driver_args += [
                f"+partition-fpga-topo={partition_config.metasim_partition_topo_args()}"
            ]
            permissive_driver_args += [
                f"+partition-fpga-cnt={partition_config.fpga_cnt}"
            ]
            permissive_driver_args += [
                f"+partition-fpga-idx={partition_config.node.pidx}"
            ]

            # Disable heartbeat checking for partitions
            permissive_driver_args += [f"+partitioned=1"]

            permissive_driver_args += [f"+slotid={slotid}"]
            permissive_driver_args += [f"+batch-size={partition_config.batch_size()}"]

            command_cutbridgeidxs = array_to_plusargs(cutbridge_idxs, "+cutbridgeidx")
            permissive_driver_args += command_cutbridgeidxs

            peer_pcis_offsets = partition_config.get_pcim_slot_and_bridge_offsets()
            command_pcisoffsets = array_to_plusargs(
                peer_pcis_offsets, "+peer-pcis-offset"
            )
            permissive_driver_args += command_pcisoffsets

        if self.fased_runtime_profile is not None:
            permissive_driver_args = self._sanitize_fased_controlled_generated_tokens(
                permissive_driver_args,
                "generated permissive arguments",
                allowed_expansions=("$fased_profile_args",),
            )
            command_bootbinaries = self._sanitize_fased_controlled_generated_tokens(
                command_bootbinaries, "generated boot-binary arguments"
            )

        driver_call = f"""{need_sudo} ./{driver} +permissive {" ".join(permissive_driver_args)} {extra_plusargs_for_command} +permissive-off {" ".join(command_bootbinaries)} {extra_args_for_command} """
        base_command = (
            f"""script -f -c 'stty intr ^] && {driver_call} && stty intr ^c' uartlog"""
        )

        if profile_preflight:
            screen_wrapped = (
                f"""screen -S {screen_name} -d -m bash -c "{base_command}" && sleep 1 || exit $?"""
            )
            return (
                f"{profile_preflight}\n{screen_wrapped}\n{profile_postlaunch}"
            )
        screen_wrapped = (
            f"""screen -S {screen_name} -d -m bash -c "{base_command}"; sleep 1"""
        )
        return screen_wrapped

    def get_kill_simulation_command(self) -> str:
        driver = self.get_local_driver_binaryname()
        need_sudo = "sudo" if is_on_aws() else ""
        # Note that pkill only works for names <=15 characters
        return f"""{need_sudo} pkill -SIGKILL {driver[:15]}"""

    def handle_failure(
        self, buildresult: _stdoutString, what: str, dir: Path | str, cmd: str
    ) -> None:
        """A helper function for a nice error message when used in conjunction with the run() function"""
        if buildresult.failed:
            rootLogger.info(
                f"{self.driver_type_message} {what} failed. Exiting. See log for details."
            )
            rootLogger.info(
                f"""You can also re-run '{cmd}' in the '{dir}' directory to debug this error."""
            )
            sys.exit(1)

    def fetch_all_URI(self, dir: str) -> None:
        """Downloads all URI. Local filenames use a hash which will be re-calculated later. Duplicate downloads
        are skipped via an exists() check on the filesystem."""
        for container in self.uri_list:
            container.local_pre_download(dir, self)

    def get_local_uri_paths(self, dir: str) -> list[Tuple[str, str]]:
        """Get all paths of local URIs that were previously downloaded."""

        ret = list()
        for container in self.uri_list:
            maybe_file = container.get_rsync_path(dir, self)
            if maybe_file is not None:
                ret.append(maybe_file)
        return ret

    def verify_local_uri_path(
        self, dir: str, local_path: str, remote_path: str
    ) -> None:
        """Recheck one contracted URI cache entry immediately before rsync."""
        if self.artifact_sha256 is None:
            return
        for container in self.uri_list:
            both = container._choose_path(dir, self)
            if both is None:
                continue
            _, destination = both
            if destination == local_path and container.destination_name == remote_path:
                container.verify_local_artifact(destination, self)
                return
        raise RuntimeError(
            f"Contracted URI path is not part of HWDB entry {self.name}: "
            f"{local_path} -> {remote_path}"
        )

    def resolve_hwcfg_values(self, dir: str) -> None:
        # must be done after fetch_all_URIs
        # based on the platform, read the URI, fill out values

        if self.platform == "f2":
            return
        else:  # bitstream_tar platforms
            for container in self.uri_list:
                container._expected_sha256(self)
                both = container._choose_path(dir, self)

                # do nothing if there isn't a URI
                if both is None:
                    uri = self.bitstream_tar
                    destination = self.bitstream_tar
                else:
                    (uri, destination) = both

                if uri == self.bitstream_tar and uri is not None:
                    assert destination is not None
                    container.verify_local_artifact(destination, self)
                    # unpack destination value
                    temp_dir = f"{dir}/{URIContainer.hashed_name(uri)}-dir"
                    local(f"mkdir -p {temp_dir}")
                    local(f"tar xvf {destination} -C {temp_dir}")

                    # read string from metadata
                    cap = local(f"cat {temp_dir}/*/metadata", capture=True)
                    metadata = firesim_description_to_tags(cap)

                    self.set_platform(
                        metadata["firesim-deployquintuplet"].split("-")[0]
                    )
                    self.set_deploy_quintuplet(metadata["firesim-deployquintuplet"])
                    deploy_makefrag = metadata.get(
                        "firesim-deploymakefrag", "None"
                    )  # support old metadatas that don't have this
                    rootLogger.debug(f"Got {deploy_makefrag} from metadata")
                    self.set_deploy_makefrag(
                        deploy_makefrag if deploy_makefrag != "None" else None
                    )

                    break

    def get_partition_fpga_cnt(self) -> int:
        quintuplet_pieces = self.get_deployquintuplet_pieces_for_config()
        target_split_fpga_cnt = quintuplet_pieces[5]
        return int(target_split_fpga_cnt)

    def get_partition_fpga_idx(self) -> int:
        quintuplet_pieces = self.get_deployquintuplet_pieces_for_config()
        target_split_fpga_idx = quintuplet_pieces[6]
        if target_split_fpga_idx.isnumeric():
            return int(target_split_fpga_idx)
        else:
            rootLogger.warning(f"FPGA index {target_split_fpga_idx} is not a number")
            return self.get_partition_fpga_cnt() - 1

    def build_sim_driver(self) -> None:
        """Build driver for running simulation"""
        if self.driver_built:
            # we already built the driver at some point
            return
        # TODO there is a duplicate of this in runtools
        quintuplet_pieces = self.get_deployquintuplet_pieces_for_config()
        target_project_makefrag = self.get_deploymakefrag_for_config()

        platform = quintuplet_pieces[0]
        target_project = quintuplet_pieces[1]
        design = quintuplet_pieces[2]
        target_config = quintuplet_pieces[3]
        platform_config = quintuplet_pieces[4]
        rootLogger.info(
            f"Building {self.driver_type_message} driver for {str(self.get_deployquintuplet_for_config())}"
        )

        deploy_dir = get_deploy_dir()
        with InfoStreamLogger("stdout"), prefix(f"cd {deploy_dir}/../"), prefix(
            create_export_string(FIRESIM_BUILD_ENV_VARS)
        ), prefix("source sourceme-manager.sh --skip-ssh-setup"), prefix("cd sim/"):
            driverbuildcommand = f"make PLATFORM={self.get_platform()} TARGET_PROJECT={target_project} {extra_target_project_make_args(target_project, target_project_makefrag, deploy_dir)} DESIGN={design} TARGET_CONFIG={target_config} PLATFORM_CONFIG={platform_config} {self.get_driver_build_target()}"
            buildresult = run(driverbuildcommand)
            self.handle_failure(
                buildresult, "driver build", "firesim/sim", driverbuildcommand
            )

        self.driver_built = True

    def build_sim_tarball(
        self, paths: List[Tuple[str, str]], tarball_name: str
    ) -> None:
        """Take the simulation driver and tar it. build_sim_driver()
        must run before this function.  Rsync is used in a mode where it's copying
        from local paths to a local folder. This is confusing as rsync traditionally is
        used for copying from local folders to a remote folder. The variable local_remote_dir is
        named as a reminder that it's actually pointing at this local machine"""
        if self.tarball_built:
            # we already built it
            return

        # builddir is a temporary directory created by TemporaryDirectory()
        # the path a folder is under /tmp/ with a random name
        # After this scope block exists, the entire folder is deleted
        with TemporaryDirectory() as builddir:

            with InfoStreamLogger("stdout"), prefix(f"cd {get_deploy_dir()}"):
                for local_path, remote_path in paths:
                    # The `rsync_project()` function does not allow
                    # copying between two local directories.
                    # This uses the same option flags but operates rsync in local->local mode
                    options = "-pthrvz -L"
                    local_dir = local_path
                    local_remote_dir = pjoin(builddir, remote_path)
                    cmd = f"rsync {options} {local_dir} {local_remote_dir}"

                    results = run(cmd)
                    self.handle_failure(results, "local rsync", get_deploy_dir(), cmd)

            # This must be taken outside of a cd context
            cmd = f"mkdir -p {self.local_quintuplet_path()}"
            results = run(cmd)
            self.handle_failure(results, "local mkdir", builddir, cmd)
            absolute_tarball_path = self.local_quintuplet_path() / tarball_name

            with InfoStreamLogger("stdout"), prefix(f"cd {builddir}"):
                findcmd = 'find . -mindepth 1 -maxdepth 1 -printf "%P\n"'
                taroptions = "-czvf"

                # Running through find and xargs is the most simple way I've found to meet these requirements:
                #   * create the tar with no leading ./ or foldername
                #   * capture all types of hidden files (.a ..a .aa)
                #   * avoid capturing the parent folder (..) with globs looking for hidden files
                cmd = f"{findcmd} | xargs tar {taroptions} {absolute_tarball_path}"

                results = run(cmd)
                self.handle_failure(results, "tarball", builddir, cmd)

            self.tarball_built = True

    def __str__(self) -> str:
        return """RuntimeHWConfig: {}\nDeployQuintuplet: {}\nDeployMakefrag: {}\nAGFI: {}\nBitstream tar: {}\nCustomRuntimeConf: {}""".format(
            self.name,
            self.deploy_quintuplet,
            self.deploy_makefrag,
            self.agfi,
            self.bitstream_tar,
            str(self.customruntimeconfig),
        )


class RuntimeBuildRecipeConfig(RuntimeHWConfig):
    """A pythonic version of the entires in config_build_recipes.yaml"""

    def __init__(
        self,
        name: str,
        build_recipe_dict: Dict[str, Any],
        build_recipes_config_file: str,
        default_metasim_host_sim: str,
        metasimulation_only_plusargs: str,
        metasimulation_only_vcs_plusargs: str,
    ) -> None:
        self.name = name

        self.agfi = None
        self.bitstream_tar = None
        self.driver_tar = None
        self.tarball_built = False

        self.uri_list = []

        self.deploy_quintuplet = (
            build_recipe_dict.get("PLATFORM", "f2")
            + "-"
            + build_recipe_dict.get("TARGET_PROJECT", "firesim")
            + "-"
            + build_recipe_dict["DESIGN"]
            + "-"
            + build_recipe_dict["TARGET_CONFIG"]
            + "-"
            + build_recipe_dict["PLATFORM_CONFIG"]
        )

        # resolve the path as an absolute path if set
        self.deploy_makefrag = build_recipe_dict.get("TARGET_PROJECT_MAKEFRAG")
        # TODO: rename this since this can either be the hwdb or the build recipes file (in metasim or normal fpga sim)
        self.hwdb_file = build_recipes_config_file
        if self.deploy_makefrag:
            base = build_recipes_config_file
            abs_deploy_makefrag = resolve_path(self.deploy_makefrag, base)
            if abs_deploy_makefrag is None:
                raise Exception(
                    f"Unable to find TARGET_PROJECT_MAKEFRAG ({self.deploy_makefrag}) either as an absolute path or relative to {base}"
                )
            else:
                self.deploy_makefrag = abs_deploy_makefrag

        self.customruntimeconfig = build_recipe_dict["metasim_customruntimeconfig"]
        self.fased_runtime_profile = None
        self.artifact_sha256 = None
        # note whether we've built a copy of the simulation driver for this hwconf
        self.driver_built = False
        self.metasim_host_simulator = default_metasim_host_sim

        self.platform = build_recipe_dict.get("PLATFORM", "f2")
        self.driver_name_prefix = ""
        if self.metasim_host_simulator in ["verilator", "verilator-debug"]:
            self.driver_name_prefix = "V"

        self.local_driver_base_dir = LOCAL_DRIVERS_GENERATED_SRC

        self.driver_type_message = "Metasim"

        self.metasimulation_only_plusargs = metasimulation_only_plusargs
        self.metasimulation_only_vcs_plusargs = metasimulation_only_vcs_plusargs

        self.additional_required_files = []

        if self.metasim_host_simulator in ["vcs", "vcs-debug"]:
            self.additional_required_files.append(
                (self.get_local_driver_path() + ".daidir", "")
            )

    def get_driver_name_suffix(self) -> str:
        driver_name_suffix = ""
        if self.metasim_host_simulator in ["verilator-debug", "vcs-debug"]:
            driver_name_suffix = "-debug"
        return driver_name_suffix

    def get_driver_build_target(self) -> str:
        return self.metasim_host_simulator

    def get_boot_simulation_command(
        self,
        slotid: int,
        all_macs: Sequence[MacAddress],
        all_rootfses: Sequence[Optional[str]],
        all_linklatencies: Sequence[int],
        all_netbws: Sequence[int],
        profile_interval: int,
        all_bootbinaries: List[str],
        all_shmemportnames: List[str],
        tracerv_config: TracerVConfig,
        autocounter_config: AutoCounterConfig,
        hostdebug_config: HostDebugConfig,
        synthprint_config: SynthPrintConfig,
        partition_config: PartitionConfig,
        cutbridge_idxs: List[int],
        extra_plusargs: str,
        extra_args: str,
    ) -> str:
        """return the command used to boot the meta simulation."""
        full_extra_plusargs = (
            " " + self.metasimulation_only_plusargs + " " + extra_plusargs
        )
        if self.metasim_host_simulator in ["vcs", "vcs-debug"]:
            full_extra_plusargs = (
                " " + self.metasimulation_only_vcs_plusargs + " " + full_extra_plusargs
            )
        if self.metasim_host_simulator == "verilator-debug":
            full_extra_plusargs += " +waveformfile=metasim_waveform.vcd "
        if self.metasim_host_simulator == "vcs-debug":
            full_extra_plusargs += " +fsdbfile=metasim_waveform.fsdb "
        # TODO: spike-dasm support
        full_extra_args = " 2> metasim_stderr.out " + extra_args
        return super(RuntimeBuildRecipeConfig, self).get_boot_simulation_command(
            slotid,
            all_macs,
            all_rootfses,
            all_linklatencies,
            all_netbws,
            profile_interval,
            all_bootbinaries,
            all_shmemportnames,
            tracerv_config,
            autocounter_config,
            hostdebug_config,
            synthprint_config,
            partition_config,
            cutbridge_idxs,
            full_extra_plusargs,
            full_extra_args,
        )


class RuntimeHWDB:
    """This class manages the hardware configurations that are available
    as endpoints on the simulation."""

    hwconf_dict: Dict[str, RuntimeHWConfig]
    config_file_name: str
    simulation_mode_string: str

    def __init__(self, hardwaredbconfigfile: str) -> None:
        self.config_file_name = hardwaredbconfigfile
        self.simulation_mode_string = "FPGA simulation"

        agfidb_configfile = None
        with open(hardwaredbconfigfile, "r") as yaml_file:
            agfidb_configfile = yaml.safe_load(yaml_file)

        agfidb_dict = agfidb_configfile

        self.hwconf_dict = {
            s: RuntimeHWConfig(s, v, hardwaredbconfigfile)
            for s, v in agfidb_dict.items()
        }

    def keyerror_message(self, name: str) -> str:
        """Return the error message for lookup errors."""
        return f"'{name}' not found in '{self.config_file_name}', which is used to specify target design descriptions for {self.simulation_mode_string}s."

    def get_runtimehwconfig_from_name(self, name: str) -> RuntimeHWConfig:
        if name not in self.hwconf_dict:
            raise KeyError(self.keyerror_message(name))
        return self.hwconf_dict[name]

    def __str__(self) -> str:
        return pprint.pformat(vars(self))


class RuntimeBuildRecipes(RuntimeHWDB):
    """Same as RuntimeHWDB, but use information from build recipes entries
    instead of hwdb for metasimulation."""

    def __init__(
        self,
        build_recipes_config_file: str,
        metasim_host_simulator: str,
        metasimulation_only_plusargs: str,
        metasimulation_only_vcs_plusargs: str,
    ) -> None:
        self.config_file_name = build_recipes_config_file
        self.simulation_mode_string = "Metasimulation"

        recipes_configfile = None
        with open(build_recipes_config_file, "r") as yaml_file:
            recipes_configfile = yaml.safe_load(yaml_file)

        recipes_dict = recipes_configfile

        self.hwconf_dict = {
            s: RuntimeBuildRecipeConfig(
                s,
                v,
                build_recipes_config_file,
                metasim_host_simulator,
                metasimulation_only_plusargs,
                metasimulation_only_vcs_plusargs,
            )
            for s, v in recipes_dict.items()
        }


class InnerRuntimeConfiguration:
    """Pythonic version of config_runtime.yaml"""

    run_farm_requested_name: str
    run_farm_dispatcher: RunFarm
    topology: str
    no_net_num_nodes: int
    linklatency: int
    switchinglatency: int
    netbandwidth: int
    profileinterval: int
    launch_timeout: timedelta
    always_expand: bool
    tracerv_config: TracerVConfig
    autocounter_config: AutoCounterConfig
    hostdebug_config: HostDebugConfig
    synthprint_config: SynthPrintConfig
    partition_config: PartitionConfig
    workload_name: str
    suffixtag: str
    terminateoncompletion: bool
    metasimulation_enabled: bool
    metasimulation_host_simulator: str
    metasimulation_only_plusargs: str
    metasimulation_only_vcs_plusargs: str
    default_plusarg_passthrough: str

    def __init__(self, runtimeconfigfile: str, configoverridedata: str) -> None:

        runtime_configfile = None
        with open(runtimeconfigfile, "r") as yaml_file:
            runtime_configfile = yaml.safe_load(yaml_file)

        runtime_dict = runtime_configfile

        # override parts of the runtime conf if specified
        if configoverridedata != "":
            ## handle overriding part of the runtime conf
            configoverrideval = configoverridedata.split()
            overridesection = configoverrideval[0]
            overridefield = configoverrideval[1]
            overridevalue = configoverrideval[2]
            rootLogger.warning("Overriding part of the runtime config with: ")
            rootLogger.warning("""[{}]""".format(overridesection))
            rootLogger.warning(overridefield + "=" + overridevalue)
            runtime_dict[overridesection][overridefield] = overridevalue

        def dict_assert(key_check, dict_name):
            assert (
                key_check in dict_name
            ), f"FAIL: missing {key_check} in runtime config."

        dict_assert("metasimulation", runtime_dict)
        metasim_dict = runtime_dict["metasimulation"]
        dict_assert("metasimulation_enabled", metasim_dict)
        self.metasimulation_enabled = metasim_dict["metasimulation_enabled"]
        dict_assert("metasimulation_host_simulator", metasim_dict)
        self.metasimulation_host_simulator = metasim_dict[
            "metasimulation_host_simulator"
        ]
        dict_assert("metasimulation_only_plusargs", metasim_dict)
        self.metasimulation_only_plusargs = metasim_dict["metasimulation_only_plusargs"]
        dict_assert("metasimulation_only_vcs_plusargs", metasim_dict)
        self.metasimulation_only_vcs_plusargs = metasim_dict[
            "metasimulation_only_vcs_plusargs"
        ]

        # Setup the run farm
        defaults_file = runtime_dict["run_farm"]["base_recipe"]
        with open(defaults_file, "r") as yaml_file:
            run_farm_configfile = yaml.safe_load(yaml_file)
        run_farm_type = run_farm_configfile["run_farm_type"]
        run_farm_args = run_farm_configfile["args"]

        # add the overrides if it exists

        override_args = runtime_dict["run_farm"].get("recipe_arg_overrides")
        if override_args:
            run_farm_args = deep_merge(run_farm_args, override_args)

        run_farm_dispatch_dict = dict([(x.__name__, x) for x in inheritors(RunFarm)])

        if not run_farm_type in run_farm_dispatch_dict:
            raise Exception(
                f"Unable to find {run_farm_type} in available run farm classes: {run_farm_dispatch_dict.keys()}"
            )

        # create dispatcher object using class given and pass args to it
        self.run_farm_dispatcher = run_farm_dispatch_dict[run_farm_type](
            run_farm_args, self.metasimulation_enabled
        )

        self.topology = runtime_dict["target_config"]["topology"]
        self.no_net_num_nodes = int(runtime_dict["target_config"]["no_net_num_nodes"])
        self.linklatency = int(runtime_dict["target_config"]["link_latency"])
        self.switchinglatency = int(runtime_dict["target_config"]["switching_latency"])
        self.netbandwidth = int(runtime_dict["target_config"]["net_bandwidth"])
        self.profileinterval = int(runtime_dict["target_config"]["profile_interval"])
        self.defaulthwconfig = runtime_dict["target_config"]["default_hw_config"]

        self.tracerv_config = TracerVConfig(runtime_dict.get("tracing", {}))
        self.autocounter_config = AutoCounterConfig(runtime_dict.get("autocounter", {}))
        self.hostdebug_config = HostDebugConfig(runtime_dict.get("host_debug", {}))
        self.synthprint_config = SynthPrintConfig(runtime_dict.get("synth_print", {}))
        self.partition_config = PartitionConfig()

        dict_assert("plusarg_passthrough", runtime_dict["target_config"])
        self.default_plusarg_passthrough = runtime_dict["target_config"][
            "plusarg_passthrough"
        ]

        self.workload_name = runtime_dict["workload"]["workload_name"]
        # an extra tag to differentiate workloads with the same name in results names
        self.suffixtag = (
            runtime_dict["workload"]["suffix_tag"]
            if "suffix_tag" in runtime_dict["workload"]
            else None
        )
        self.terminateoncompletion = (
            runtime_dict["workload"]["terminate_on_completion"] == True
        )

    def __str__(self) -> str:
        return pprint.pformat(vars(self))


class RuntimeConfig:
    """This class manages the overall configuration of the manager for running
    simulation tasks."""

    launch_time: str
    args: argparse.Namespace
    runtimehwdb: RuntimeHWDB
    innerconf: InnerRuntimeConfiguration
    run_farm: RunFarm
    workload: WorkloadConfig
    firesim_topology_with_passes: FireSimTopologyWithPasses
    runtime_build_recipes: RuntimeBuildRecipes

    def __init__(self, args: argparse.Namespace) -> None:
        """This reads runtime configuration files, massages them into formats that
        the rest of the manager expects, and keeps track of other info."""
        self.launch_time = strftime("%Y-%m-%d--%H-%M-%S", gmtime())

        self.args = args

        self.innerconf = InnerRuntimeConfiguration(
            args.runtimeconfigfile, args.overrideconfigdata
        )
        rootLogger.debug(self.innerconf)

        self.run_farm = self.innerconf.run_farm_dispatcher

        # for enumeration check if platform actually needs it
        if args.task == "enumeratefpgas" and not self.run_farm.needs_fpga_enumeration():
            rootLogger.info("Skipping FPGA enumeration - platform discover BDF dynamically")
            return

        
        # construct pythonic db of hardware configurations available to us at
        # runtime.
        self.runtimehwdb = RuntimeHWDB(args.hwdbconfigfile)
        rootLogger.debug(self.runtimehwdb)       

        self.runtime_build_recipes = RuntimeBuildRecipes(
            args.buildrecipesconfigfile,
            self.innerconf.metasimulation_host_simulator,
            self.innerconf.metasimulation_only_plusargs,
            self.innerconf.metasimulation_only_vcs_plusargs,
        )
        rootLogger.debug(self.runtime_build_recipes)

        # setup workload config obj, aka a list of workloads that can be assigned
        # to a server
        if args.task != "enumeratefpgas":
            self.workload = WorkloadConfig(
                self.innerconf.workload_name, self.launch_time, self.innerconf.suffixtag
            )
        else:
            self.workload = WorkloadConfig(
                "null.json", self.launch_time, self.innerconf.suffixtag
            )

        # start constructing the target configuration tree
        self.firesim_topology_with_passes = FireSimTopologyWithPasses(
            self.innerconf.topology,
            self.innerconf.no_net_num_nodes,
            self.run_farm,
            self.runtimehwdb,
            self.innerconf.defaulthwconfig,
            self.workload,
            self.innerconf.linklatency,
            self.innerconf.switchinglatency,
            self.innerconf.netbandwidth,
            self.innerconf.profileinterval,
            self.innerconf.tracerv_config,
            self.innerconf.autocounter_config,
            self.innerconf.hostdebug_config,
            self.innerconf.synthprint_config,
            self.innerconf.partition_config,
            self.innerconf.terminateoncompletion,
            self.runtime_build_recipes,
            self.innerconf.metasimulation_enabled,
            self.innerconf.default_plusarg_passthrough,
        )

    def launch_run_farm(self) -> None:
        """directly called by top-level launchrunfarm command."""
        self.run_farm.launch_run_farm()

    def terminate_run_farm(self) -> None:
        """directly called by top-level terminaterunfarm command."""
        terminate_some_dict = {}
        if self.args.terminatesome is not None:
            for pair in self.args.terminatesome:
                terminate_some_dict[pair[0]] = pair[1]

        def old_style_terminate_args(instance_type, arg_val, arg_flag_str):
            if arg_val != -1:
                rootLogger.critical(
                    "WARNING: You are using the old-style "
                    + arg_flag_str
                    + " flag. See the new --terminatesome flag in help. The old-style flag will be removed in the next major FireSim release (1.15.X)."
                )
                terminate_some_dict[instance_type] = arg_val

        # TODO: update terminatesome for f2
        old_style_terminate_args(
            "f1.16xlarge", self.args.terminatesomef116, "--terminatesomef116"
        )
        old_style_terminate_args(
            "f1.4xlarge", self.args.terminatesomef14, "--terminatesomef14"
        )
        old_style_terminate_args(
            "f1.2xlarge", self.args.terminatesomef12, "--terminatesomef12"
        )
        old_style_terminate_args(
            "m4.16xlarge", self.args.terminatesomem416, "--terminatesomem416"
        )

        self.run_farm.terminate_run_farm(terminate_some_dict, self.args.forceterminate)

    def infrasetup(self) -> None:
        """directly called by top-level infrasetup command."""
        # set this to True if you want to use mock boto3 instances for testing
        # the manager.
        use_mock_instances_for_testing = False
        self.firesim_topology_with_passes.infrasetup_passes(
            use_mock_instances_for_testing
        )

    def build_driver(self) -> None:
        """directly called by top-level builddriver command."""
        self.firesim_topology_with_passes.build_driver_passes()

    def enumerate_fpgas(self) -> None:
        """directly called by top-level enumeratefpgas command."""
        # if platform dosnt need enum, return
        if not hasattr(self, 'firesim_topology_with_passes'):
            return
        
        use_mock_instances_for_testing = False        
        self.firesim_topology_with_passes.enumerate_fpgas_passes(
            use_mock_instances_for_testing
        )

    def boot(self) -> None:
        """directly called by top-level boot command."""
        use_mock_instances_for_testing = False
        self.firesim_topology_with_passes.boot_simulation_passes(
            use_mock_instances_for_testing
        )

    def kill(self) -> None:
        use_mock_instances_for_testing = False
        self.firesim_topology_with_passes.kill_simulation_passes(
            use_mock_instances_for_testing
        )

    def run_workload(self) -> None:
        use_mock_instances_for_testing = False
        self.firesim_topology_with_passes.run_workload_passes(
            use_mock_instances_for_testing
        )
