"""
Resolution of the configuration directory (storage location for credentials/),
with a fixed priority:

1. Explicit override (e.g. --config-dir in the CLI, or a parameter passed from
   another application such as the future Home Assistant integration)
2. Already-set environment variable HOERMOLES_CONF_DIR
3. HOERMOLES_CONF_DIR from a .env file (searched upward starting at the
   current working directory). Never overrides an already-set real
   environment variable from step 2 - that's the default behavior of
   python-dotenv's load_dotenv() (no override=True).
4. Default: ~/.hoermoles

For development, a .env pointing HOERMOLES_CONF_DIR at a scratch directory
outside the repo keeps test credentials separate from "real" ones under
~/.hoermoles.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ENV_VAR_CONFIG_DIR = "HOERMOLES_CONF_DIR"

_DEFAULT_CONFIG_DIR = Path.home() / ".hoermoles"


def resolve_config_dir(override: str | Path | None = None) -> Path:
    if override is not None:
        return Path(override).expanduser().resolve()

    load_dotenv()
    value = os.environ.get(ENV_VAR_CONFIG_DIR)
    if value:
        return Path(value).expanduser().resolve()

    return _DEFAULT_CONFIG_DIR
