"""SSH configuration helpers for the FireSim manager."""

from __future__ import annotations

import os
from typing import Mapping, Optional


FIRESIM_SSH_KEY_ENV = "FIRESIM_SSH_KEY"
DEFAULT_FIRESIM_SSH_KEY = "~/firesim.pem"


def get_manager_ssh_key_path(
    environment: Optional[Mapping[str, str]] = None,
) -> str:
    """Return the configured manager SSH private-key path.

    An unset or empty ``FIRESIM_SSH_KEY`` preserves FireSim's historical
    ``~/firesim.pem`` default. Tilde expansion is supported for either value.
    """
    environment = os.environ if environment is None else environment
    configured_path = environment.get(FIRESIM_SSH_KEY_ENV)
    return os.path.expanduser(configured_path or DEFAULT_FIRESIM_SSH_KEY)
